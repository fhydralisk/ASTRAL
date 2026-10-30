"""Local implementation; owns scientific state, never user authentication."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid
import zipfile

from .base import Download, HarnessService, ServiceError
from .environment import StrictEnvironment
from .events import event_batch, event_download
from .operations import build_operations
from .records import _number_records, _with_core_derivatives, _strip_detail
from .session import InteractiveSession
from .redaction import register, scrub

ROLES = ("search", "data", "evaluator")
PROVIDERS = {
    "openrouter": "OPENROUTER",
    "openai": "COMPATIBLE",
    "azure": "OPENAI",
    "compatible": "COMPATIBLE",
    "deepseek": "DEEPSEEK",
    "siliconflow": "SILICONFLOW",
    "gemini": "GEMINI",
    "lmstudio": "LMSTUDIO",
}
STARTS = {"start": "search", "prepare_data": "data", "start_evaluator_assistance": "evaluator"}


class LocalHarnessService(HarnessService):
    def __init__(self, root: str | Path, *, global_tasks=8, per_user_tasks=2):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._admission = threading.Lock()
        self._sessions: dict[str, InteractiveSession] = {}
        self._call_locks: dict[str, threading.RLock] = {}
        self._records = {}
        self._active: dict[tuple[str, str], str] = {}
        self.global_tasks, self.per_user_tasks = global_tasks, per_user_tasks
        for directory in self.root.iterdir():
            if directory.is_dir() and (directory / "metadata.json").is_file():
                self._records[directory.name] = json.loads(
                    (directory / "metadata.json").read_text(encoding="utf-8")
                )
        self._stop = threading.Event()
        self._writer = threading.Thread(
            target=self._checkpoint_loop, daemon=True, name="harness-checkpoint"
        )
        self._writer.start()

    def _write(self, path, value):
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8"
        )
        temporary.replace(path)

    def _metadata(self, sid):
        if not re.fullmatch(r"[a-f0-9]{32}", sid) or sid not in self._records:
            raise ServiceError(404, "Session not found", code="session_not_found")
        return self._records[sid]

    @staticmethod
    def _tags(tags):
        if len(tags) > 16 or any(
            not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", k) or not isinstance(v, str) or len(v) > 256
            for k, v in tags.items()
        ):
            raise ServiceError(422, "Invalid session tags")
        return dict(tags)

    def create(self, *, tags, idempotency_key):
        tags = self._tags(tags)
        if not idempotency_key or len(idempotency_key) > 200:
            raise ServiceError(422, "Idempotency key required")
        with self._lock:
            existing = next(
                (r for r in self._records.values() if r["creation_key"] == idempotency_key), None
            )
            if existing:
                if existing["tags"] != tags:
                    raise ServiceError(409, "Idempotency key already used with different tags")
                return self._public(existing)
            sid = uuid.uuid4().hex
            record = {
                "id": sid,
                "tags": tags,
                "archived": False,
                "created_at": time.time(),
                "creation_key": idempotency_key,
                "commands": {},
            }
            (self.root / sid).mkdir()
            self._write(self.root / sid / "metadata.json", record)
            self._records[sid] = record
            return self._public(record)

    @staticmethod
    def _public(record):
        return {k: v for k, v in record.items() if k not in {"creation_key", "commands"}}

    def list_sessions(self, tags=None):
        with self._lock:
            return [
                self._public(r)
                for r in self._records.values()
                if all(r["tags"].get(k) == v for k, v in (tags or {}).items())
            ]

    def update(self, session_id, *, tags=None, archived=None):
        with self._lock:
            self._metadata(session_id)
            command_lock = self._call_locks.setdefault(session_id, threading.RLock())
        with command_lock, self._lock:
            record = self._metadata(session_id)
            session = self._sessions.get(session_id)
            if (
                archived
                and session is not None
                and (
                    any(
                        t and t.is_alive()
                        for t in (
                            session.thread,
                            session.data_thread,
                            session.evaluator_agent_thread,
                        )
                    )
                    or any(
                        m.state == "paused"
                        for m in (
                            session.sr_interaction_manager,
                            session.data_interaction_manager,
                            session.evaluator_interaction_manager,
                        )
                    )
                )
            ):
                raise ServiceError(409, "Stop active agents before archiving", code="session_busy")
            if tags is not None:
                record["tags"] = self._tags(tags)
            if archived is not None:
                record["archived"] = bool(archived)
            self._write(self.root / session_id / "metadata.json", record)
            return self._public(record)

    def _session(self, sid):
        with self._lock:
            self._metadata(sid)
            if sid in self._sessions:
                return self._sessions[sid]
            load_lock = self._call_locks.setdefault(sid, threading.RLock())
        with load_lock:
            if sid in self._sessions:
                return self._sessions[sid]
            directory = self.root / sid
            session = InteractiveSession(
                directory,
                run_dir=directory / "runs",
                workspace_path=directory / "workspace",
                service_mode=True,
            )
            session.conversation_id = sid
            snapshot = directory / "snapshot.json"
            if snapshot.is_file():
                session.restore_persistent_state(json.loads(snapshot.read_text(encoding="utf-8")))
            with self._lock:
                self._sessions[sid] = session
            return session

    def _prune(self):
        for key in list(self._active):
            session = self._sessions[key[0]]
            role = key[1]
            thread = getattr(
                session,
                {"search": "thread", "data": "data_thread", "evaluator": "evaluator_agent_thread"}[
                    role
                ],
            )
            manager = getattr(
                session,
                {
                    "search": "sr_interaction_manager",
                    "data": "data_interaction_manager",
                    "evaluator": "evaluator_interaction_manager",
                }[role],
            )
            if not (thread and thread.is_alive()) and manager.state != "paused":
                del self._active[key]

    def invoke(self, session_id, operation, parameters, *, idempotency_key=None):
        if operation == "operation_status":
            with self._lock:
                record = self._metadata(session_id)
                command = record["commands"].get(parameters["operation_id"])
                if command is None:
                    raise ServiceError(404, "Operation not found", code="operation_not_found")
                return scrub(dict(command["result"]))
        session = self._session(session_id)
        if operation == "start" and idempotency_key:
            parameters = {
                **parameters,
                "payload": {**parameters.get("payload", {}), "idempotency_key": idempotency_key},
            }
        # Serialize state mutations, but reads do not hold the command lock during model probes.
        if operation in {
            "status",
            "records",
            "record",
            "control_status",
            "event_download",
            "candidates",
        } or operation.endswith("_events"):
            return scrub(self._execute(session, operation, parameters))
        with self._call_locks[session_id]:
            record = self._metadata(session_id)
            if record["archived"]:
                raise ServiceError(409, "Session is archived")
            digest = hashlib.sha256(
                json.dumps([operation, parameters], sort_keys=True).encode()
            ).hexdigest()
            if idempotency_key:
                previous = record["commands"].get(idempotency_key)
                if previous:
                    if previous["digest"] != digest:
                        raise ServiceError(409, "Idempotency key reused with different command")
                    return previous["result"]
            role = STARTS.get(operation)
            if role:
                if not session.context.args.agent_environments[role].get("_configured"):
                    raise ServiceError(
                        409,
                        "Model configuration must be supplied before execution",
                        code="credentials_required",
                    )
                with self._admission:
                    self._prune()
                    key = (session_id, role)
                    owner = record["tags"].get("user_ref", session_id)
                    if key not in self._active:
                        if (
                            len(self._active) >= self.global_tasks
                            or sum(v == owner for v in self._active.values()) >= self.per_user_tasks
                        ):
                            raise ServiceError(429, "Agent capacity exceeded", code="task_capacity")
                        self._active[key] = owner
            if idempotency_key:
                record["commands"][idempotency_key] = {
                    "digest": digest,
                    "result": {"operation_id": idempotency_key, "status": "pending_or_interrupted"},
                }
                self._write(self.root / session_id / "metadata.json", record)
            try:
                result = scrub(self._execute(session, operation, parameters))
                if idempotency_key and (operation in STARTS or operation == "control_command"):
                    result = {
                        "operation_id": idempotency_key,
                        "run_id": session.run_id,
                        "status": "accepted",
                    }
            except BaseException as error:
                if idempotency_key and not getattr(error, "started", False):
                    record["commands"].pop(idempotency_key, None)
                    self._write(self.root / session_id / "metadata.json", record)
                if role:
                    with self._admission:
                        self._prune()
                raise
            if idempotency_key:
                record["commands"][idempotency_key] = {"digest": digest, "result": result}
                self._write(self.root / session_id / "metadata.json", record)
            self._checkpoint(session_id)
            return result

    def _execute(self, session, operation, parameters):
        if operation == "control_status":
            return session.sr_interaction_manager.status()
        if operation in {"control_events", "event_download"}:
            role = parameters.get("role", "search")
            if role not in ROLES:
                raise ServiceError(422, "Unknown agent role")
            manager = getattr(
                session,
                {
                    "search": "sr_interaction_manager",
                    "data": "data_interaction_manager",
                    "evaluator": "evaluator_interaction_manager",
                }[role],
            )
            if operation == "event_download":
                return event_download(manager, int(parameters["sequence"]), role)
            return event_batch(manager, max(0, int(parameters.get("after_seq", 0))))
        if operation == "control_command":
            role = parameters.get("role", "search")
            if role not in ROLES:
                raise ServiceError(422, "Unknown agent role")
            manager = getattr(
                session,
                {
                    "search": "sr_interaction_manager",
                    "data": "data_interaction_manager",
                    "evaluator": "evaluator_interaction_manager",
                }[role],
            )
            return manager.command(parameters["action"], parameters.get("message"))
        if operation == "candidates":
            state = session.run_state
            records = state.ranked_candidates() if state else []
            if parameters.get("mode", "topk") == "pareto" and state:
                indices = set(state.pareto_indices(records))
                records = [r for index, r in enumerate(records) if index in indices]
            import sr_harness_engine as engine

            result = []
            for record in records[:1000]:
                value = record.display_dict()
                try:
                    value["formula_latex"] = engine.parse(record.formula).to_str(latex=True)
                except Exception:
                    value["formula_latex"] = record.formula
                result.append(value)
            return {"records": result}
        if operation in {"records", "record"}:
            state = session.run_state
            records = _number_records(state.records(include_detail=True)) if state else []
            by_id = {r["node_id"]: r for r in records}
            if operation == "record":
                found = next((r for r in records if r["node_id"] == parameters["node_id"]), None)
                if not found:
                    raise ServiceError(404, "Search node not found")
                return _with_core_derivatives(found, by_id)
            return {
                "records": [
                    _strip_detail(_with_core_derivatives(r, by_id))
                    for r in records
                    if r["seq"] > int(parameters.get("after_seq", 0))
                ][:32]
            }
        functions = build_operations(session)
        if operation not in functions:
            raise ServiceError(404, "Unknown operation")
        if operation in {"test_model", "test_data_agent_model", "test_evaluator_agent_model"}:
            role = {
                "test_model": "search",
                "test_data_agent_model": "data",
                "test_evaluator_agent_model": "evaluator",
            }[operation]
            session.context.args.probe_environment = session.context.args.agent_environments[role]
        return functions[operation](**parameters)

    def credentials(self, session_id, role, configuration):
        if role not in ROLES:
            raise ServiceError(422, "Unknown agent role")
        provider = configuration["provider"]
        if provider not in PROVIDERS:
            raise ServiceError(422, "Unsupported provider")
        prefix = PROVIDERS[provider]
        endpoint = configuration.get("endpoint", "")
        if endpoint and not re.match(r"^https?://", endpoint):
            raise ServiceError(422, "Endpoint must use HTTP or HTTPS")
        key = configuration.get("api_key", "")
        if (
            not isinstance(key, str)
            or not key.strip()
            or any(c in key for c in "\r\n\0")
            or len(key) > 16384
        ):
            raise ServiceError(422, "Invalid key")
        if (
            provider == "siliconflow"
            and endpoint
            and not endpoint.rstrip("/").endswith("/chat/completions")
        ):
            endpoint = endpoint.rstrip("/") + "/chat/completions"
        register(key)
        session = self._session(session_id)
        env = StrictEnvironment({f"{prefix}_API_KEY": key, "_configured": "1"})
        if provider == "openai" and not endpoint:
            endpoint = "https://api.openai.com/v1"
        if endpoint:
            env[f"{prefix}_ENDPOINT"] = endpoint
        if provider in {"azure", "openai"}:
            env["OPENAI_API_VERSION"] = configuration.get("api_version", "2025-04-01-preview")
            env["OPENAI_OLDTIME_ENDPOINT"] = endpoint
        with self._call_locks[session_id]:
            # Replace, never mutate: an in-flight request retains its prior configuration.
            session.context.args.agent_environments[role] = env
            settings = {
                "llm_provider": "openai"
                if provider == "azure"
                else "compatible"
                if provider == "openai"
                else provider,
                "llm_model": configuration["model"],
            }
            current = (
                session.settings
                if role == "search"
                else session.data_agent_settings
                if role == "data"
                else session.evaluator_agent_settings
            )
            if provider == "gemini" and current.get("tool_parser") == "openai":
                settings["tool_parser"] = "text"
            if role == "search":
                session.configure(settings)
            elif role == "data":
                session.configure_data_agent(settings)
            else:
                session.configure_evaluator_agent(settings)

    def upload(self, session_id, path, stream):
        session = self._session(session_id)
        with self._call_locks[session_id], session.lock:
            if self._metadata(session_id)["archived"]:
                raise ServiceError(409, "Session is archived")
            destination = session.resolve(path, access="create")
            if destination.exists():
                raise ServiceError(409, "File already exists")
            parent = str(Path(path).parent)
            if parent != ".":
                session.workspace_manager.create_directory(parent, parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".upload-", dir=session.workspace)
            size = 0
            try:
                with os.fdopen(descriptor, "wb") as output:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        size += len(chunk)
                        if size > 256 * 1024 * 1024:
                            raise ServiceError(413, "Maximum file size is 256 MiB")
                        output.write(chunk)
                session.workspace_manager.replace_file(Path(temporary), path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            session.data_interaction_manager.publish_event(
                "workspace_changed", {"path": path, "size": size}
            )
            self._checkpoint(session_id)
            return {"path": path, "size": size}

    def export(self, session_id):
        self._session(session_id)
        with self._call_locks[session_id]:
            self._checkpoint(session_id)
            descriptor, filename = tempfile.mkstemp(suffix=".zip")
            os.close(descriptor)
            with zipfile.ZipFile(filename, "w", zipfile.ZIP_DEFLATED) as archive:
                for file in (self.root / session_id).rglob("*"):
                    if (
                        file.is_file()
                        and not file.is_symlink()
                        and file.name not in {"metadata.json", ".env"}
                    ):
                        archive.write(file, file.relative_to(self.root / session_id))

            def chunks():
                with open(filename, "rb") as stream:
                    yield from iter(lambda: stream.read(1024 * 1024), b"")

            return Download(
                chunks(),
                f"{session_id}.zip",
                "application/zip",
                lambda: Path(filename).unlink(missing_ok=True),
            )

    def _checkpoint(self, sid):
        session = self._sessions.get(sid)
        if session is not None:
            self._write(self.root / sid / "snapshot.json", scrub(session.export_persistent_state()))

    def _checkpoint_loop(self):
        while not self._stop.wait(5):
            for sid in list(self._sessions):
                try:
                    with self._call_locks[sid]:
                        self._checkpoint(sid)
                except Exception:
                    # Never log exceptions containing provider response bodies or keys.
                    pass

    def close(self):
        self._stop.set()
        self._writer.join(timeout=2)
        for sid, session in list(self._sessions.items()):
            for manager in (
                session.sr_interaction_manager,
                session.data_interaction_manager,
                session.evaluator_interaction_manager,
            ):
                if manager.state != "idle":
                    manager.command("stop")
            for thread in (session.thread, session.data_thread, session.evaluator_agent_thread):
                if thread and thread.is_alive():
                    thread.join(timeout=2)
            with self._call_locks[sid]:
                self._checkpoint(sid)
