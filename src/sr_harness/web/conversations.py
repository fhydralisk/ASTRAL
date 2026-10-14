"""Persistent conversation registry for the interactive Web workbench."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from .session import InteractiveSession

if TYPE_CHECKING:
    from ..runtime.workspace import Workspace


CLIENT_COOKIE = "sr_harness_client"
CONVERSATION_HEADER = "X-SR-Harness-Conversation"
CONVERSATION_QUERY = "conversation"
DEFAULT_CONVERSATION_NAME = "Unnamed Conversation"
# This is a cache lifetime, not a browser-visible conversation lifetime. An
# evicted transient is reconstructed with the same ID from the next request.
TRANSIENT_IDLE_SECONDS = 60 * 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConversationSessionProxy:
    """Resolve attribute access to the session bound to the current request."""

    def __init__(self, registry: "ConversationRegistry"):
        object.__setattr__(self, "_registry", registry)
        object.__setattr__(self, "_current", ContextVar("sr_harness_session", default=None))

    def bind(self, session: InteractiveSession):
        return self._current.set(session)

    def reset(self, token) -> None:
        self._current.reset(token)

    def current_session(self) -> InteractiveSession:
        session = self._current.get()
        if session is None:
            raise RuntimeError("No InteractiveSession is bound to the current request")
        return session

    def __getattr__(self, name: str):
        return getattr(self.current_session(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self.current_session(), name, value)


class ConversationRegistry:
    """Persist conversation metadata and lazily own one session per conversation."""

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        workspace_files: list[str] | None = None,
        isolate_users: bool = False,
        run_root: str | Path | None = None,
        persist_sessions: bool = False,
        persistence_interval: float = 5.0,
        read_only: bool = False,
    ):
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.read_only = bool(read_only)
        if self.read_only:
            if not self.workspace_dir.is_dir():
                raise FileNotFoundError(
                    f"Read-only workspace directory does not exist: {self.workspace_dir}"
                )
        else:
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.workspace_dir / "conversations.json"
        self.visit_log_path = self.workspace_dir / "conversation-visits.jsonl"
        self.workspaces_dir = self.workspace_dir / "workspaces"
        self.sessions_dir = self.workspace_dir / "sessions"
        self.runs_dir = (
            Path(run_root).expanduser().resolve()
            if run_root is not None else self.workspace_dir / "runs"
        )
        if not self.read_only:
            self.workspaces_dir.mkdir(exist_ok=True)
            self.sessions_dir.mkdir(exist_ok=True)
            self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_files = list(workspace_files or [])
        self.isolate_users = bool(isolate_users)
        if self.read_only and self.workspace_files:
            raise ValueError("Read-only conversation registries cannot add workspace mounts")
        self.persist_sessions = bool(persist_sessions) and not self.read_only
        self.persistence_interval = max(1.0, float(persistence_interval))
        self.lock = threading.RLock()
        self._persistence_stop = threading.Event()
        self._persistence_thread: threading.Thread | None = None
        self._persistence_error: Exception | None = None
        self._sessions: dict[str, InteractiveSession] = {}
        self._session_locks: dict[str, threading.Lock] = {}
        self._transient_records: dict[str, dict[str, Any]] = {}
        self._transient_clients: dict[str, str] = {}
        self._transient_roots: dict[str, tempfile.TemporaryDirectory] = {}
        self._transient_last_seen: dict[str, float] = {}
        self._active_requests: dict[str, int] = {}
        self._retired_transient_roots: dict[str, tempfile.TemporaryDirectory] = {}
        self._records = self._load_records()
        if not self._records and self.read_only:
            raise ValueError("Read-only conversation registry contains no conversations")
        self.session_proxy = ConversationSessionProxy(self)
        if self.persist_sessions:
            self._persistence_thread = threading.Thread(
                target=self._persistence_loop,
                name="sr-harness-session-persistence",
                daemon=True,
            )
            self._persistence_thread.start()

    @property
    def default_session(self) -> InteractiveSession:
        with self.lock:
            record = next((item for item in self._records if not item["archived"]), None)
            if record is None:
                if self.read_only:
                    raise RuntimeError("Read-only conversation registry has no active conversation")
                record = self._create_record(owner_id=None)
        return self._session_for(record)

    def _load_records(self) -> list[dict[str, Any]]:
        if not self.manifest_path.exists():
            if self.read_only:
                raise FileNotFoundError(
                    f"Read-only conversation registry does not exist: {self.manifest_path}"
                )
            return []
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Unable to load conversation registry: {exc}") from exc
        if not isinstance(payload, dict) or set(payload) != {"version", "conversations"}:
            raise ValueError("Conversation registry does not match the current schema")
        if payload["version"] != 1:
            raise ValueError("Unsupported conversation registry version")
        records = payload["conversations"]
        if not isinstance(records, list):
            raise ValueError("Conversation registry must contain a conversations list")
        required = {
            "id", "name", "owner_id", "workspace", "run_dir", "created_at",
            "updated_at", "archived",
        }
        for record in records:
            if not isinstance(record, dict) or set(record) != required:
                raise ValueError("Conversation registry contains an invalid record")
            if not all(
                isinstance(record[key], str) and record[key]
                for key in required - {"owner_id", "archived"}
            ):
                raise ValueError("Conversation registry record fields must be non-empty strings")
            if record["owner_id"] is not None and not isinstance(record["owner_id"], str):
                raise ValueError("Conversation owner_id must be a string or None")
            if not isinstance(record["archived"], bool):
                raise ValueError("Conversation archived must be a boolean")
        return records

    def _write_records(self, records: list[dict[str, Any]] | None = None) -> None:
        if self.read_only:
            raise PermissionError("Conversation registry is read-only")
        payload = {"version": 1, "conversations": records if records is not None else self._records}
        temporary = self.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.manifest_path)

    def _create_record(
        self,
        *,
        owner_id: str | None,
        name: str | None = None,
    ) -> dict[str, Any]:
        if self.read_only:
            raise PermissionError("Conversation registry is read-only")
        if name is None:
            name = DEFAULT_CONVERSATION_NAME
        else:
            name = name.strip()
            if not name:
                raise ValueError("Conversation name cannot be empty")
        conversation_id = uuid.uuid4().hex
        created_at = _now()
        run_dir = self.runs_dir / conversation_id
        try:
            stored_run_dir = str(run_dir.relative_to(self.workspace_dir))
        except ValueError:
            stored_run_dir = str(run_dir)
        record = {
            "id": conversation_id,
            "name": name,
            "owner_id": owner_id,
            "workspace": str(Path("workspaces") / conversation_id),
            "run_dir": stored_run_dir,
            "created_at": created_at,
            "updated_at": created_at,
            "archived": False,
        }
        workspace = self.workspace_dir / record["workspace"]
        workspace.mkdir(parents=True, exist_ok=False)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._session_dir(record).mkdir(parents=True, exist_ok=True)
        self._records.append(record)
        self._write_records()
        return record

    def _append_visit_event(
        self,
        event: str,
        *,
        client_id: str,
        transient_id: str,
        conversation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        """Append an analytics event without turning a visit into a conversation."""
        if self.read_only:
            return
        payload = {
            "timestamp": _now(),
            "event": event,
            "visitor_id": client_id,
            "transient_id": transient_id,
        }
        if conversation_id is not None:
            payload["conversation_id"] = conversation_id
        if reason is not None:
            payload["reason"] = reason
        with self.visit_log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _create_transient_record(
        self,
        client_id: str,
        *,
        name: str | None = None,
        source: str = "visit",
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a temporary browser session that is absent from the registry manifest."""
        if self.read_only:
            raise PermissionError("Conversation registry is read-only")
        if name is None:
            name = DEFAULT_CONVERSATION_NAME
        else:
            name = name.strip()
            if not name:
                raise ValueError("Conversation name cannot be empty")
        conversation_id = conversation_id or uuid.uuid4().hex
        temporary = tempfile.TemporaryDirectory(prefix="sr-harness-visit-")
        root = Path(temporary.name)
        created_at = _now()
        record = {
            "id": conversation_id,
            "name": name,
            "owner_id": client_id if self.isolate_users else None,
            "workspace": str(root / "workspace"),
            "run_dir": str(root / "run"),
            "created_at": created_at,
            "updated_at": created_at,
            "archived": False,
        }
        (root / "workspace").mkdir()
        (root / "run").mkdir()
        (root / "session").mkdir()
        self._transient_records[conversation_id] = record
        self._transient_clients[conversation_id] = client_id
        self._transient_roots[conversation_id] = temporary
        self._transient_last_seen[conversation_id] = time.monotonic()
        self._append_visit_event(
            "visit_started",
            client_id=client_id,
            transient_id=conversation_id,
            reason=source,
        )
        return record

    def _transient_visible(self, record: dict[str, Any], client_id: str) -> bool:
        return self._transient_clients.get(record["id"]) == client_id

    def _reusable_transient_id(self, selected_id: str | None) -> str | None:
        """Return a safe expired transient ID that can be reconstructed."""
        if selected_id is None or len(selected_id) != 32:
            return None
        try:
            if uuid.UUID(hex=selected_id).hex != selected_id:
                return None
        except ValueError:
            return None
        if (
            selected_id in self._transient_records
            or any(record["id"] == selected_id for record in self._records)
        ):
            return None
        return selected_id

    def _retire_transient_root(
        self,
        conversation_id: str,
        temporary: tempfile.TemporaryDirectory | None,
    ) -> None:
        if temporary is None:
            return
        if self._active_requests.get(conversation_id, 0):
            self._retired_transient_roots[conversation_id] = temporary
        else:
            temporary.cleanup()

    def _drop_transient(self, conversation_id: str) -> None:
        session = self._sessions.pop(conversation_id, None)
        if session is not None:
            session.interrupt_active_work()
        self._transient_records.pop(conversation_id, None)
        self._transient_clients.pop(conversation_id, None)
        self._transient_last_seen.pop(conversation_id, None)
        temporary = self._transient_roots.pop(conversation_id, None)
        self._retire_transient_root(conversation_id, temporary)

    def _sweep_transients(self) -> None:
        cutoff = time.monotonic() - TRANSIENT_IDLE_SECONDS
        expired = [
            conversation_id
            for conversation_id, last_seen in self._transient_last_seen.items()
            if last_seen < cutoff and not self._active_requests.get(conversation_id, 0)
        ]
        for conversation_id in expired:
            self._drop_transient(conversation_id)

    def acquire(self, conversation_id: str) -> None:
        with self.lock:
            self._active_requests[conversation_id] = (
                self._active_requests.get(conversation_id, 0) + 1
            )

    def release(self, conversation_id: str) -> None:
        with self.lock:
            remaining = self._active_requests.get(conversation_id, 0) - 1
            if remaining > 0:
                self._active_requests[conversation_id] = remaining
                return
            self._active_requests.pop(conversation_id, None)
            temporary = self._retired_transient_roots.pop(conversation_id, None)
            if temporary is not None:
                temporary.cleanup()

    def _materialize(
        self,
        record: dict[str, Any],
        *,
        client_id: str,
        reason: str,
    ) -> tuple[dict[str, Any], InteractiveSession]:
        """Promote a temporary visit to a durable conversation before mutation."""
        conversation_id = record["id"]
        if conversation_id not in self._transient_records:
            return record, self._session_for(record)
        transient_session = self._sessions.pop(conversation_id, None)
        snapshot = (
            transient_session.export_persistent_state()
            if transient_session is not None
            else None
        )
        old_workspace = self._record_path(record, "workspace")
        old_run_dir = self._record_path(record, "run_dir")
        old_session_dir = self._session_dir(record)
        workspace = self.workspaces_dir / conversation_id
        run_dir = self.runs_dir / conversation_id
        session_dir = self.sessions_dir / conversation_id
        shutil.copytree(old_workspace, workspace)
        shutil.copytree(old_run_dir, run_dir)
        shutil.copytree(old_session_dir, session_dir)
        try:
            stored_run_dir = str(run_dir.relative_to(self.workspace_dir))
        except ValueError:
            stored_run_dir = str(run_dir)
        record["workspace"] = str(Path("workspaces") / conversation_id)
        record["run_dir"] = stored_run_dir
        record["updated_at"] = _now()
        self._transient_records.pop(conversation_id)
        self._transient_clients.pop(conversation_id)
        self._transient_last_seen.pop(conversation_id, None)
        temporary = self._transient_roots.pop(conversation_id)
        self._retire_transient_root(conversation_id, temporary)
        self._records.append(record)
        self._write_records()
        session = self._session_for(record)
        if snapshot is not None:
            session.restore_persistent_state(snapshot)
        self._append_visit_event(
            "conversation_persisted",
            client_id=client_id,
            transient_id=conversation_id,
            conversation_id=conversation_id,
            reason=reason,
        )
        return record, session

    def _record_path(self, record: dict[str, Any], field: str) -> Path:
        path = Path(record[field])
        return path if path.is_absolute() else self.workspace_dir / path

    def _session_dir(self, record: dict[str, Any]) -> Path:
        temporary = self._transient_roots.get(record["id"])
        if temporary is not None:
            return Path(temporary.name) / "session"
        return self.sessions_dir / record["id"]

    def _session_for(self, record: dict[str, Any]) -> InteractiveSession:
        conversation_id = record["id"]
        with self.lock:
            session = self._sessions.get(conversation_id)
            if session is not None:
                return session
            session_lock = self._session_locks.setdefault(conversation_id, threading.Lock())
        with session_lock:
            with self.lock:
                session = self._sessions.get(conversation_id)
                if session is not None:
                    return session
                workspace = self._record_path(record, "workspace")
                session_dir = self._session_dir(record)
                run_dir = self._record_path(record, "run_dir")
                snapshot_path = session_dir / "interactive-session.json"
            if self.read_only:
                missing = [path for path in (workspace, session_dir, run_dir) if not path.is_dir()]
                if missing:
                    raise FileNotFoundError(
                        "Read-only conversation storage is incomplete: "
                        + ", ".join(str(path) for path in missing)
                    )
            else:
                workspace.mkdir(parents=True, exist_ok=True)
                session_dir.mkdir(parents=True, exist_ok=True)
            session = InteractiveSession(
                run_dir.parent,
                workspace_files=self.workspace_files,
                run_dir=run_dir,
                workspace_path=workspace,
                env_path=session_dir / ".env",
                read_only=self.read_only,
            )
            session.conversation_id = conversation_id
            if (self.persist_sessions or self.read_only) and snapshot_path.is_file():
                try:
                    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    session.restore_persistent_state(snapshot)
                except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"Unable to restore conversation {conversation_id}: {exc}"
                    ) from exc
            with self.lock:
                self._sessions[conversation_id] = session
            return session

    def _session_snapshot_path(self, record: dict[str, Any]) -> Path:
        return self._session_dir(record) / "interactive-session.json"

    def persist(self) -> None:
        """Atomically persist every materialized InteractiveSession."""
        if not self.persist_sessions:
            return
        with self.lock:
            pairs = [
                (record, self._sessions[record["id"]])
                for record in self._records
                if record["id"] in self._sessions
            ]
        for record, session in pairs:
            snapshot_path = self._session_snapshot_path(record)
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = snapshot_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(session.export_persistent_state(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(snapshot_path)
        self._persistence_error = None

    def _persistence_loop(self) -> None:
        while not self._persistence_stop.wait(self.persistence_interval):
            try:
                self.persist()
            except Exception as exc:
                self._persistence_error = exc

    def _visible(self, record: dict[str, Any], client_id: str) -> bool:
        return not record["archived"] and (
            not self.isolate_users or record["owner_id"] == client_id
        )

    def _owned(self, record: dict[str, Any], client_id: str) -> bool:
        return not self.isolate_users or record["owner_id"] == client_id

    def _raise_persistence_error(self) -> None:
        if self._persistence_error is not None:
            raise RuntimeError("InteractiveSession persistence failed") from self._persistence_error

    def resolve(
        self,
        client_id: str,
        selected_id: str | None,
        *,
        materialize_reason: str | None = None,
    ) -> tuple[dict[str, Any], InteractiveSession]:
        with self.lock:
            self._raise_persistence_error()
            self._sweep_transients()
            visible = [record for record in self._records if self._visible(record, client_id)]
            transient = self._transient_records.get(selected_id or "")
            if transient is not None and self._transient_visible(transient, client_id):
                record = transient
                self._transient_last_seen[record["id"]] = time.monotonic()
            else:
                record = next((item for item in visible if item["id"] == selected_id), None)
                if record is None and visible and (
                    selected_id is not None or self.read_only or self.isolate_users
                ):
                    record = visible[0]
                if record is None:
                    if self.read_only:
                        raise RuntimeError("No conversation is visible in read-only mode")
                    reusable_id = self._reusable_transient_id(selected_id)
                    record = self._create_transient_record(
                        client_id,
                        source="visit_resumed" if reusable_id is not None else "visit",
                        conversation_id=reusable_id,
                    )
            if materialize_reason is not None:
                return self._materialize(
                    record,
                    client_id=client_id,
                    reason=materialize_reason,
                )
        return record, self._session_for(record)

    def list(self, client_id: str, selected_id: str | None = None) -> dict[str, Any]:
        with self.lock:
            records = [record for record in self._records if self._visible(record, client_id)]
            records.extend(
                record
                for record in self._transient_records.values()
                if self._transient_visible(record, client_id)
            )
            return {
                "isolate_users": self.isolate_users,
                "read_only": self.read_only,
                "selected": selected_id,
                "conversations": [
                    {key: record[key] for key in ("id", "name", "created_at", "updated_at")}
                    for record in records
                ],
            }

    def materialize(
        self,
        client_id: str,
        conversation_id: str,
        reason: str,
    ) -> tuple[dict[str, Any], InteractiveSession]:
        """Make a selected temporary conversation durable."""
        with self.lock:
            transient = self._transient_records.get(conversation_id)
            if transient is not None:
                if not self._transient_visible(transient, client_id):
                    raise KeyError(conversation_id)
                return self._materialize(
                    transient,
                    client_id=client_id,
                    reason=reason,
                )
            record = next(
                (
                    item
                    for item in self._records
                    if item["id"] == conversation_id and self._visible(item, client_id)
                ),
                None,
            )
            if record is None:
                raise KeyError(conversation_id)
            return record, self._session_for(record)

    def create(self, client_id: str, name: str | None = None) -> dict[str, Any]:
        if self.read_only:
            raise PermissionError("Conversation registry is read-only")
        with self.lock:
            for conversation_id, record in list(self._transient_records.items()):
                if self._transient_visible(record, client_id):
                    self._drop_transient(conversation_id)
            record = self._create_transient_record(client_id, name=name, source="new_conversation")
            if name is not None:
                record, _ = self._materialize(
                    record,
                    client_id=client_id,
                    reason="conversation_named",
                )
            return record

    def select(self, client_id: str, conversation_id: str) -> dict[str, Any]:
        with self.lock:
            transient = self._transient_records.get(conversation_id)
            if transient is not None and self._transient_visible(transient, client_id):
                record = transient
            else:
                record = next(
                    (
                        item
                        for item in self._records
                        if item["id"] == conversation_id and self._visible(item, client_id)
                    ),
                    None,
                )
                if record is None:
                    raise KeyError(conversation_id)
        self._session_for(record)
        return record

    def rename(self, client_id: str, conversation_id: str, name: str) -> dict[str, Any]:
        if self.read_only:
            raise PermissionError("Conversation registry is read-only")
        name = name.strip()
        if not name:
            raise ValueError("Conversation name cannot be empty")
        if len(name) > 120:
            raise ValueError("Conversation name cannot exceed 120 characters")
        with self.lock:
            record = self.select(client_id, conversation_id)
            record, _ = self._materialize(
                record,
                client_id=client_id,
                reason="conversation_renamed",
            )
            record["name"] = name
            record["updated_at"] = _now()
            self._write_records()
            return record

    def archive(
        self,
        client_id: str,
        conversation_id: str,
        selected_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Archive a conversation and choose the conversation that remains selected."""
        if self.read_only:
            raise PermissionError("Conversation registry is read-only")
        with self.lock:
            transient = self._transient_records.get(conversation_id)
            if transient is not None and self._transient_visible(transient, client_id):
                archived = dict(transient, archived=True, updated_at=_now())
                self._drop_transient(conversation_id)
                visible = [item for item in self._records if self._visible(item, client_id)]
                if not visible:
                    visible = [
                        self._create_transient_record(
                            client_id,
                            source="archive_replacement",
                        )
                    ]
                selected = next(
                    (item for item in visible if item["id"] == selected_id),
                    visible[0],
                )
                return archived, selected
            record = next(
                (
                    item
                    for item in self._records
                    if item["id"] == conversation_id
                    and self._owned(item, client_id)
                    and not item["archived"]
                ),
                None,
            )
            if record is None:
                raise KeyError(conversation_id)
            record["archived"] = True
            record["updated_at"] = _now()
            visible = [item for item in self._records if self._visible(item, client_id)]
            if not visible:
                visible = [self._create_transient_record(client_id, source="archive_replacement")]
            selected = next((item for item in visible if item["id"] == selected_id), visible[0])
            self._write_records()
            return record, selected

    @staticmethod
    def _write_tree(
        archive: zipfile.ZipFile,
        root: Path,
        prefix: str,
        *,
        workspace: Workspace | None = None,
    ) -> None:
        if not root.exists():
            return
        opener = workspace.safe_open if workspace is not None else open
        for current, directory_names, file_names in os.walk(root, followlinks=False):
            current_path = Path(current)
            directory_names[:] = sorted(
                name for name in directory_names
                if not (current_path / name).is_symlink()
            )
            for name in sorted(file_names):
                path = current_path / name
                if name == ".env" or path.is_symlink():
                    continue
                relative = Path(prefix) / path.relative_to(root)
                with opener(path, "rb") as input_stream:
                    with archive.open(relative.as_posix(), "w") as output_stream:
                        shutil.copyfileobj(input_stream, output_stream)

    def export(self, client_id: str, conversation_id: str) -> tuple[Path, str]:
        """Create a temporary ZIP containing a conversation and its retained state."""
        record = self.select(client_id, conversation_id)
        session = self._session_for(record)
        with self.lock:
            metadata = {key: record[key] for key in ("id", "name", "created_at", "updated_at")}
            snapshot = session.export_persistent_state()
            workspace = self._record_path(record, "workspace")
            run_dir = self._record_path(record, "run_dir")
        descriptor, archive_name = tempfile.mkstemp(suffix=".zip")
        os.close(descriptor)
        Path(archive_name).unlink(missing_ok=True)
        try:
            with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(
                    "conversation.json",
                    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                )
                archive.writestr(
                    "interactive-session.json",
                    json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
                )
                self._write_tree(
                    archive,
                    workspace,
                    "workspace",
                    workspace=session.workspace_manager,
                )
                self._write_tree(archive, run_dir, "run")
        except Exception:
            Path(archive_name).unlink(missing_ok=True)
            raise
        return Path(archive_name), f"conversation-{conversation_id}.zip"

    def close(self) -> None:
        self._persistence_stop.set()
        if self._persistence_thread is not None:
            self._persistence_thread.join(timeout=self.persistence_interval + 1)
        with self.lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.interrupt_active_work()
        for session in sessions:
            for thread in (session.thread, session.data_thread, session.evaluator_agent_thread):
                if thread:
                    thread.join(timeout=2)
        self.persist()
        for temporary in [
            *self._transient_roots.values(),
            *self._retired_transient_roots.values(),
        ]:
            temporary.cleanup()
        self._transient_roots.clear()
        self._retired_transient_roots.clear()


def mount_conversations(app, registry: ConversationRegistry) -> None:
    """Bind browser identity, conversation selection, and registry endpoints."""

    def persistence_timing(request: Request) -> tuple[str | None, str | None]:
        path = request.url.path
        method = request.method
        agent_routes = {
            ("POST", "/api/session/start"),
            ("POST", "/api/data/agent"),
            ("POST", "/api/evaluator/agent/start"),
            ("POST", "/api/control/command"),
        }
        if (method, path) in agent_routes:
            return "agent_used", None
        workspace_mutation = (
            (path.startswith("/api/workspace") and method in {"POST", "PUT", "PATCH", "DELETE"})
            or (method, path) in {
                ("POST", "/api/data/demo"),
                ("PUT", "/api/data/selection"),
                ("PUT", "/api/data/descriptions"),
                ("PUT", "/api/evaluator"),
            }
        )
        return (None, "workspace_modified") if workspace_mutation else (None, None)

    @app.middleware("http")
    async def bind_conversation(request: Request, call_next):
        client_id = request.cookies.get(CLIENT_COOKIE) or uuid.uuid4().hex
        path = request.url.path
        if path in {"/", "/viewer", "/api/version"} or path.startswith("/static/"):
            request.state.client_id = client_id
            response = await call_next(request)
            response.set_cookie(
                CLIENT_COOKIE, client_id, httponly=True, samesite="lax", max_age=31536000
            )
            return response
        selected_id = (
            request.headers.get(CONVERSATION_HEADER)
            or request.query_params.get(CONVERSATION_QUERY)
        )
        before_reason, after_reason = persistence_timing(request)
        record, session = await run_in_threadpool(
            registry.resolve,
            client_id,
            selected_id,
            materialize_reason=before_reason,
        )
        request.state.client_id = client_id
        request.state.conversation_id = record["id"]
        registry.acquire(record["id"])
        token = registry.session_proxy.bind(session)
        try:
            response = await call_next(request)
            if after_reason is not None and response.status_code < 400:
                registry.materialize(client_id, record["id"], after_reason)
        finally:
            registry.session_proxy.reset(token)
            registry.release(record["id"])
        response.set_cookie(
            CLIENT_COOKIE, client_id, httponly=True, samesite="lax", max_age=31536000
        )
        return response

    @app.get("/api/conversations")
    def conversations(request: Request):
        return registry.list(request.state.client_id, request.state.conversation_id)

    @app.post("/api/conversations")
    def create_conversation(request: Request, payload: dict = Body(default={})):
        record = registry.create(
            request.state.client_id, str(payload.get("name", "")).strip() or None
        )
        return {key: record[key] for key in ("id", "name", "created_at", "updated_at")}

    @app.post("/api/conversations/{conversation_id}/select")
    def select_conversation(conversation_id: str, request: Request):
        try:
            record = registry.select(request.state.client_id, conversation_id)
        except KeyError as exc:
            raise HTTPException(404, "Conversation not found") from exc
        return {"selected": record["id"]}

    @app.patch("/api/conversations/{conversation_id}")
    def rename_conversation(conversation_id: str, request: Request, payload: dict = Body(...)):
        try:
            record = registry.rename(
                request.state.client_id, conversation_id, str(payload.get("name", ""))
            )
        except KeyError as exc:
            raise HTTPException(404, "Conversation not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {key: record[key] for key in ("id", "name", "created_at", "updated_at")}

    @app.delete("/api/conversations/{conversation_id}")
    def archive_conversation(conversation_id: str, request: Request):
        try:
            record, selected = registry.archive(
                request.state.client_id,
                conversation_id,
                request.state.conversation_id,
            )
        except KeyError as exc:
            raise HTTPException(404, "Conversation not found") from exc
        return {"archived": record["id"], "selected": selected["id"]}

    @app.get("/api/conversations/{conversation_id}/export")
    def export_conversation(conversation_id: str, request: Request):
        try:
            archive, filename = registry.export(request.state.client_id, conversation_id)
        except KeyError as exc:
            raise HTTPException(404, "Conversation not found") from exc
        return FileResponse(
            archive,
            filename=filename,
            media_type="application/zip",
            background=BackgroundTask(archive.unlink, missing_ok=True),
        )
