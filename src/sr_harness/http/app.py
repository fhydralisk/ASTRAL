"""Authenticated internal HTTP adapter. Scientific state is accessible only via HarnessService."""

from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import os
import tempfile
from typing import Any, Literal
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.background import BackgroundTask

from ..service.base import Download, HarnessService, ServiceError
from ..service.redaction import scrub
from .isolation import RequestWorkPool, RequestBodyLimit, request_work_keys
from .responses import worker_json_response


class CreateSession(BaseModel):
    tags: dict[str, str] = Field(default_factory=dict, max_length=16)
    idempotency_key: str = Field(min_length=1, max_length=200)


class UpdateSession(BaseModel):
    tags: dict[str, str] | None = None
    archived: bool | None = None


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal[
        "openrouter",
        "openai",
        "azure",
        "compatible",
        "deepseek",
        "siliconflow",
        "gemini",
        "lmstudio",
    ]
    model: str = Field(min_length=1, max_length=256)
    endpoint: str = Field(default="", max_length=2048)
    api_key: SecretStr
    api_version: str | None = None


class Command(BaseModel):
    role: Literal["search", "data", "evaluator"] = "search"
    action: str
    message: str | None = None


class SessionInfo(BaseModel):
    id: str
    tags: dict[str, str]
    archived: bool
    created_at: float


class SessionPage(BaseModel):
    sessions: list[SessionInfo]


class SessionStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    state: str
    run_id: str
    context_ready: bool
    settings: dict[str, Any]
    topk_records: list[dict[str, Any]]


class AsyncOperation(BaseModel):
    model_config = ConfigDict(extra="allow")
    operation_id: str
    state: str | None = None
    run_id: str | None = None


class Event(BaseModel):
    model_config = ConfigDict(extra="allow")
    seq: int
    kind: str
    payload: dict[str, Any]


class EventBatch(BaseModel):
    model_config = ConfigDict(extra="allow")
    events: list[Event]
    truncated: bool
    discarded_through: int
    cursor_reset: bool
    has_more: bool = False


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


def create_app(service: HarnessService, *, token: str | None = None):
    token = token or os.environ.get("HARNESS_SERVICE_TOKEN", "")
    if len(token) < 24:
        raise ValueError("HARNESS_SERVICE_TOKEN must contain at least 24 characters")
    pool = RequestWorkPool()

    @asynccontextmanager
    async def lifespan(app):
        pool.start()
        yield
        pool.close()
        service.close()

    app = FastAPI(
        title="ASTRAL Harness",
        version="1.0.0",
        lifespan=lifespan,
        responses={
            status: {"model": ErrorEnvelope}
            for status in (400, 401, 403, 404, 409, 413, 422, 429, 500, 503, 504)
        },
    )
    app.state.work_pool = pool

    @app.middleware("http")
    async def authenticate(request: Request, call_next):
        if request.url.path != "/health" and not hmac.compare_digest(
            request.headers.get("authorization", ""), "Bearer " + token
        ):
            return JSONResponse(
                {"error": {"code": "unauthorized", "message": "Invalid service credentials"}},
                status_code=401,
            )
        parts = request.url.path.split("/")
        key = parts[3] if len(parts) > 3 and parts[2] == "sessions" else "service"
        binding = request_work_keys.set(("session:" + key,))
        try:
            return await call_next(request)
        finally:
            request_work_keys.reset(binding)

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(
            {"error": {"code": exc.code, "message": scrub(str(exc.detail))}},
            status_code=exc.status_code,
        )

    @app.exception_handler(HTTPException)
    async def transport_error(request, exc):
        return JSONResponse(
            {"error": {"code": "transport_error", "message": scrub(str(exc.detail))}},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {"error": {"code": "invalid_fields", "message": "Invalid request fields"}},
            status_code=422,
        )

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(
            {"error": {"code": "invalid_request", "message": "Invalid operation parameters"}},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "execution_failed",
                    "message": "Operation failed; inspect session state before retrying",
                }
            },
            status_code=500,
        )

    def response(result):
        if isinstance(result, Download):
            return StreamingResponse(
                result.chunks,
                media_type=result.media_type,
                headers={
                    "Content-Disposition": "attachment; filename*=UTF-8''" + quote(result.filename)
                },
                background=BackgroundTask(result.close),
            )
        return worker_json_response(result)

    async def invoke(session_id, operation, parameters, key=None):
        parameters = {
            name: value.model_dump(exclude_unset=True) if isinstance(value, BaseModel) else value
            for name, value in parameters.items()
        }
        result = response(
            await pool.run(service.invoke, session_id, operation, parameters, idempotency_key=key)
        )
        if key:
            result.status_code = 202
        return result

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/sessions", status_code=201, response_model=SessionInfo)
    async def create(payload: CreateSession):
        return await pool.run(service.create, **payload.model_dump())

    @app.get("/v1/sessions", response_model=SessionPage)
    async def sessions(user_ref: str | None = None):
        return {
            "sessions": await pool.run(
                service.list_sessions, {"user_ref": user_ref} if user_ref else None
            )
        }

    @app.patch("/v1/sessions/{session_id}", response_model=SessionInfo)
    async def update(session_id: str, payload: UpdateSession):
        return await pool.run(service.update, session_id, **payload.model_dump(exclude_unset=True))

    @app.put("/v1/sessions/{session_id}/credentials/{role}", status_code=204)
    async def credentials(
        session_id: str, role: Literal["search", "data", "evaluator"], payload: ModelConfiguration
    ):
        values = payload.model_dump(exclude_none=True)
        values["api_key"] = payload.api_key.get_secret_value()
        await pool.run(service.credentials, session_id, role, values)

    @app.post(
        "/v1/sessions/{session_id}/control/command", status_code=202, response_model=AsyncOperation
    )
    async def command(
        session_id: str,
        payload: Command,
        idempotency_key: str = Header(min_length=1, max_length=200),
    ):
        return await invoke(session_id, "control_command", payload.model_dump(), idempotency_key)

    @app.get("/v1/sessions/{session_id}/control/status")
    async def control_status(session_id: str):
        return await invoke(session_id, "control_status", {})

    @app.get("/v1/sessions/{session_id}/operations/{operation_id}", response_model=AsyncOperation)
    async def operation_status(session_id: str, operation_id: str):
        return await invoke(session_id, "operation_status", {"operation_id": operation_id})

    @app.get("/v1/sessions/{session_id}/control/events", response_model=EventBatch)
    async def events(session_id: str, after_seq: int = 0, role: str = "search"):
        return await invoke(session_id, "control_events", {"after_seq": after_seq, "role": role})

    @app.get("/v1/sessions/{session_id}/control/events/{sequence}")
    async def download_search_event(session_id: str, sequence: int):
        return await invoke(session_id, "event_download", {"sequence": sequence, "role": "search"})

    @app.get("/v1/sessions/{session_id}/data/agent/events/{sequence}")
    async def download_data_event(session_id: str, sequence: int):
        return await invoke(session_id, "event_download", {"sequence": sequence, "role": "data"})

    @app.get("/v1/sessions/{session_id}/evaluator/agent/events/{sequence}")
    async def download_evaluator_event(session_id: str, sequence: int):
        return await invoke(
            session_id, "event_download", {"sequence": sequence, "role": "evaluator"}
        )

    @app.get("/v1/sessions/{session_id}/records")
    async def records(session_id: str, after_seq: int = 0):
        return await invoke(session_id, "records", {"after_seq": after_seq})

    @app.get("/v1/sessions/{session_id}/candidates")
    async def candidates(session_id: str, mode: Literal["topk", "pareto"] = "topk"):
        return await invoke(session_id, "candidates", {"mode": mode})

    @app.get("/v1/sessions/{session_id}/records/{node_id}")
    async def record(session_id: str, node_id: str):
        return await invoke(session_id, "record", {"node_id": node_id})

    @app.get("/v1/sessions/{session_id}/export")
    async def export(session_id: str):
        return response(await pool.run(service.export, session_id))

    @app.put("/v1/sessions/{session_id}/workspace/upload")
    async def upload(session_id: str, request: Request, path: str):
        # Spool to disk using bounded chunks; no scientific filesystem access in the transport.
        with tempfile.TemporaryFile() as stream:
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > 256 * 1024 * 1024:
                    raise HTTPException(413, "Maximum upload size is 256 MiB")
                await pool.run(stream.write, chunk)
            stream.seek(0)
            return await pool.run(service.upload, session_id, path, stream)

    from .scientific_routes import mount

    mount(app, invoke)
    app.add_middleware(RequestBodyLimit)
    return app
