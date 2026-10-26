from __future__ import annotations

import asyncio
import json
import math
import re
from contextlib import asynccontextmanager
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import sr_harness_engine as engine
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from ..runtime import SRInteractionManager
from .responses import worker_json_response, worker_event_response, worker_event_download
from .isolation import RequestWorkPool, RequestBodyLimit, install_route_isolation

WEB_DIR = Path(__file__).resolve().parent
STATIC_DIR = WEB_DIR / "static"
DEFAULT_LOG_DIR = Path.cwd() / "logs"


def create_app(
    log_dir: str | Path = DEFAULT_LOG_DIR,
    *,
    session=None,
    conversation_registry=None,
    read_only: bool = False,
) -> FastAPI:
    """Create and configure the SRHarness FastAPI web application.

    Args:
        log_dir: Directory where run logs and search records are stored.
        session: Active interactive session (or session proxy) for the workbench.
        conversation_registry: Optional persistent registry managing multi-conversation state.
        read_only: Whether to serve existing conversations in read-only mode.

    Returns:
        FastAPI: Configured FastAPI application instance.
    """
    version = package_version("sr-harness")
    work_pool = RequestWorkPool()

    @asynccontextmanager
    async def lifespan(app):
        work_pool.start()
        try:
            yield
        finally:
            work_pool.close()

    app = FastAPI(title="SRHarness Search Viewer", version=version, lifespan=lifespan)
    app.state.work_pool = work_pool
    install_route_isolation(app, work_pool)
    app.state.log_dir = Path(log_dir).resolve()
    app.state.session = session
    app.state.conversation_registry = conversation_registry
    app.state.read_only = bool(
        read_only or getattr(conversation_registry, "read_only", False)
    )
    app.state.interaction_manager = SRInteractionManager() if session is None else None

    @app.middleware("http")
    async def enforce_read_only(request: Request, call_next):
        if app.state.read_only and request.method not in {"GET", "HEAD", "OPTIONS"}:
            path = request.url.path
            selection = (
                request.method == "POST"
                and re.fullmatch(r"/api/conversations/[^/]+/select", path) is not None
            )
            pure_computation = request.method == "POST" and path == "/api/data/context/heatmap"
            if not (selection or pure_computation):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "SRHarness is running in read-only mode"},
                )
        return await call_next(request)
    if conversation_registry is not None:
        from .conversations import mount_conversations
        mount_conversations(app, conversation_registry)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / ("platform.html" if session is not None else "index.html"))

    @app.get("/viewer")
    async def viewer():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health", include_in_schema=False)
    async def health():
        return {"status": "ok"}

    @app.get("/api/version")
    async def application_version():
        return {"version": version}

    if session is not None:
        from .platform import mount_platform
        mount_platform(app, session)

    @app.get("/api/runs")
    def list_runs():
        state = getattr(session, "run_state", None) if session is not None else None
        if state is None:
            return {"runs": []}
        count = state.node_count
        return {"runs": [{
            "run_id": state.run_id,
            "run_key": state.run_id,
            "manifest": {"run_id": state.run_id},
            "record_count": count,
            "last_seq": count,
        }]}

    @app.get("/api/control/status")
    def control_status():
        manager = session.sr_interaction_manager if session is not None else app.state.interaction_manager
        return manager.status()

    @app.get("/api/control/events")
    def control_events(after_seq: int = Query(0, ge=0)):
        manager = session.sr_interaction_manager if session is not None else app.state.interaction_manager
        return worker_event_response(manager, after_seq)

    @app.get("/api/control/events/{sequence}")
    def download_control_event(sequence: int):
        manager = session.sr_interaction_manager if session is not None else app.state.interaction_manager
        return worker_event_download(manager, sequence, "search")

    @app.post("/api/control/command")
    def control_command(payload: dict = Body(...)):
        try:
            manager = session.sr_interaction_manager if session is not None else app.state.interaction_manager
            return manager.command(
                str(payload.get("action", "")),
                str(payload.get("message", "")) or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/records")
    def list_records(run_id: str, after_seq: int = Query(0, ge=0), include_detail: bool = False):
        state = _resolve_run_state(session, run_id)
        all_records = _number_records(state.records(include_detail=True))
        records_by_id = {
            record["node_id"]: record for record in all_records if record.get("node_id")
        }
        records = []
        for record in all_records:
            if int(record.get("seq", 0)) <= after_seq:
                continue
            record = _with_core_derivatives(record, records_by_id)
            records.append(record if include_detail else _strip_detail(record))
        return worker_json_response({"records": records})

    @app.get("/api/runs/{run_id}/records/{node_id}")
    def get_record(run_id: str, node_id: str):
        state = _resolve_run_state(session, run_id)
        all_records = _number_records(state.records(include_detail=True))
        records_by_id = {
            record["node_id"]: record for record in all_records if record.get("node_id")
        }
        for record in all_records:
            if record.get("node_id") == node_id:
                return worker_json_response(_with_core_derivatives(record, records_by_id))
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")

    @app.get("/api/runs/{run_id}/stream")
    async def stream_records(run_id: str, request: Request, after_seq: int = Query(0, ge=0)):
        state = _resolve_run_state(session, run_id)

        def encode_batch(next_seq):
            batch = []
            all_records = _number_records(state.records(include_detail=True))
            records_by_id = {record["node_id"]: record for record in all_records if record.get("node_id")}
            for record in all_records:
                seq = int(record.get("seq", 0))
                if seq > next_seq:
                    batch.append(_strip_detail(_with_core_derivatives(record, records_by_id)))
                    next_seq = max(next_seq, seq)
                    if len(batch) >= 32:
                        break
            payload = worker_json_response(_sanitize_json_value({"records": batch})).body.decode('utf-8') if batch else None
            return next_seq, payload

        async def event_source():
            next_seq = after_seq
            while not await request.is_disconnected():
                try:
                    next_seq, payload = await work_pool.run(encode_batch, next_seq)
                except HTTPException as exc:
                    yield "event: error\ndata: " + json.dumps({"detail": exc.detail}) + "\n\n"
                    return
                if payload is not None:
                    yield f"data: {payload}\n\n"
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(1.0)

        return StreamingResponse(event_source(), media_type="text/event-stream")

    app.add_middleware(RequestBodyLimit)
    return app


def _resolve_run_state(session, run_id: str):
    state = getattr(session, "run_state", None) if session is not None else None
    if state is None or state.run_id != run_id:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return state


def _number_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach Web-only cursors without storing them in the search state."""
    return [dict(record, seq=index) for index, record in enumerate(records, 1)]


def _sanitize_json_value(value: Any) -> Any:
    """Return a standards-compliant JSON value by replacing non-finite floats."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(item) for item in value]
    return value


def _strip_detail(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k != "detail"}


def _with_core_derivatives(
    record: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    record = _with_formula_latex(record)
    return _with_tool_summary(record, records_by_id or {})


def _with_formula_latex(record: dict[str, Any]) -> dict[str, Any]:
    core = record.get("core")
    if not isinstance(core, dict) or core.get("formula_latex"):
        return record
    formula = core.get("formula")
    if not formula:
        return record
    record = dict(record)
    core = dict(core)
    try:
        core["formula_latex"] = engine.parse(str(formula).replace("^", "**")).to_str(latex=True)
    except Exception:
        core["formula_latex"] = None
    record["core"] = core
    return record


def _with_tool_summary(
    record: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    core = record.get("core")
    if not isinstance(core, dict) or core.get("tool_summary"):
        return record
    record = dict(record)
    core = dict(core)
    output_counts: dict[str, int] = {}
    for name in core.get("tool_names") or []:
        if name:
            output_counts[str(name)] = output_counts.get(str(name), 0) + 1
    prompt_counts = _prompt_tool_counts(record.get("detail", {}).get("prompt", []))
    ancestor_counts = _ancestor_tool_counts(record, records_by_id)
    for name, count in ancestor_counts.items():
        prompt_counts[name] = max(prompt_counts.get(name, 0), count)
    names = sorted(set(prompt_counts) | set(output_counts))
    core["tool_summary"] = [
        {
            "name": name,
            "display_name": name.replace("_", " ").title(),
            "prompt_count": prompt_counts.get(name, 0),
            "output_count": output_counts.get(name, 0),
        }
        for name in names
    ]
    record["core"] = core
    return record


def _ancestor_tool_counts(
    record: dict[str, Any],
    records_by_id: dict[str, dict[str, Any]],
    seen: set[str] | None = None,
) -> dict[str, int]:
    seen = seen or set()
    counts: dict[str, int] = {}
    for parent in record.get("parents") or []:
        if not isinstance(parent, dict):
            continue
        parent_id = parent.get("node_id")
        if not parent_id or parent_id in seen:
            continue
        parent_record = records_by_id.get(parent_id)
        if not parent_record:
            continue
        seen.add(parent_id)
        for name in (parent_record.get("core") or {}).get("tool_names") or []:
            if name:
                name = str(name)
                counts[name] = counts.get(name, 0) + 1
        for name, count in _ancestor_tool_counts(parent_record, records_by_id, seen).items():
            counts[name] = counts.get(name, 0) + count
    return counts


def _prompt_tool_counts(prompt: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not isinstance(prompt, list):
        return counts
    for msg in prompt:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") == "tool" and msg.get("name"):
            name = str(msg["name"])
            counts[name] = counts.get(name, 0) + 1
    if counts:
        return counts
    for msg in prompt:
        if not isinstance(msg, dict):
            continue
        for call in msg.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            name = call.get("name") or (call.get("function") or {}).get("name")
            if name:
                name = str(name)
                counts[name] = counts.get(name, 0) + 1
    return counts
