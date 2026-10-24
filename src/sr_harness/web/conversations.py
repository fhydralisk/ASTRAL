"""Persistent conversation registry for the interactive Web workbench."""

from __future__ import annotations

import json
import logging
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
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from .session import InteractiveSession
from .isolation import request_work_keys, request_session_lease, request_mutating

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
    """Request-scoped proxy that forwards attribute access to the active :class:`InteractiveSession`."""

    def __init__(self, registry: "ConversationRegistry"):
        """Initialize the session proxy bound to a :class:`ConversationRegistry`.

        Args:
            registry: Conversation registry providing the fallback default session.
        """
        object.__setattr__(self, "_registry", registry)
        object.__setattr__(self, "_current", ContextVar("sr_harness_session", default=None))

    def bind(self, session: InteractiveSession):
        """Bind ``session`` to the current async/thread request context.

        Args:
            session: Active :class:`InteractiveSession` for the current HTTP request.

        Returns:
            Token: Contextvar token that can be passed to :meth:`reset`.
        """
        return self._current.set(session)

    def reset(self, token) -> None:
        """Restore the previous request-context session binding.

        Args:
            token: Contextvar reset token returned by :meth:`bind`.
        """
        self._current.reset(token)

    def current_session(self) -> InteractiveSession:
        """Return the :class:`InteractiveSession` bound to the current request context.

        Returns:
            InteractiveSession: Active session for the current request.
        """
        session = self._current.get()
        if session is None:
            raise RuntimeError("No InteractiveSession is bound to the current request")
        return session

    def __getattr__(self, name: str):
        return getattr(self.current_session(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self.current_session(), name, value)


class ConversationRegistry:
    """Persistent registry managing multi-conversation metadata, workspaces, and lazy session loading."""

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
        """Initialize the conversation registry and load existing records from ``conversations.json``.

        Args:
            workspace_dir: Root directory storing ``conversations.json``, ``workspaces/``, and ``sessions/``.
            workspace_files: Optional list of host paths mounted read-only into every conversation workspace.
            isolate_users: Whether to scope conversation listings per browser visitor cookie.
            run_root: Optional root directory where per-conversation run logs are saved.
            persist_sessions: Whether to periodically save session snapshots to disk.
            persistence_interval: Minimum interval in seconds between background snapshot writes.
            read_only: Whether to serve existing conversations without allowing state mutations.
        """
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
        self._active_lock = threading.Lock()
        self._persistence_stop = threading.Event()
        self._persistence_thread: threading.Thread | None = None
        self._persistence_errors: dict[str, Exception] = {}
        self._saved_idle_revisions: dict[str, str] = {}
        self._sessions: dict[str, InteractiveSession] = {}
        self._session_locks: dict[str, threading.Lock] = {}
        self._transient_records: dict[str, dict[str, Any]] = {}
        self._transient_clients: dict[str, str] = {}
        self._transient_roots: dict[str, tempfile.TemporaryDirectory] = {}
        self._transient_last_seen: dict[str, float] = {}
        self._active_requests: dict[str, int] = {}
        self._retired_transient_roots: dict[str, tempfile.TemporaryDirectory] = {}
        self._read_only_refresh_at = 0.0
        self.read_only_refresh_interval = 30.0
        self._snapshot_signatures: dict[str, tuple[int, int, int] | None] = {}
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
        """Return the default active :class:`InteractiveSession` instance.

        Returns:
            InteractiveSession: Default interactive session.
        """
        self._refresh_read_only()
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

    @staticmethod
    def _snapshot_signature(path: Path) -> tuple[int, int, int] | None:
        try:
            stat = path.stat()
            return stat.st_ino, stat.st_mtime_ns, stat.st_size
        except FileNotFoundError:
            return None

    def _refresh_read_only(self) -> None:
        """Refresh metadata and invalidate changed snapshots at most every 30 seconds.

        Existing requests retain their session object; subsequent requests lazily
        restore the new snapshot in a worker thread. No source files are written.
        """
        if not self.read_only:
            return
        with self.lock:
            now = time.monotonic()
            if now < self._read_only_refresh_at:
                return
            self._read_only_refresh_at = now + self.read_only_refresh_interval
            try:
                records = self._load_records()
                signatures = {
                    record["id"]: self._snapshot_signature(self._session_snapshot_path(record))
                    for record in records if record["id"] in self._sessions
                }
            except (OSError, ValueError):
                # Keep the last usable view during a transient source read failure.
                return
            self._records = records
            for conversation_id in list(self._sessions):
                if (conversation_id not in signatures or
                        signatures[conversation_id] != self._snapshot_signatures.get(conversation_id)):
                    self._sessions.pop(conversation_id, None)
                    self._snapshot_signatures.pop(conversation_id, None)

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
        with self._active_lock:
            if self._active_requests.get(conversation_id, 0):
                self._retired_transient_roots[conversation_id] = temporary
                return
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
        """Increment the active request lease count for ``conversation_id``.

        Args:
            conversation_id: Identifier of the conversation being accessed.
        """
        with self._active_lock:
            self._active_requests[conversation_id] = (
                self._active_requests.get(conversation_id, 0) + 1
            )

    def release(self, conversation_id: str) -> None:
        """Decrement the active request lease count for ``conversation_id``.

        Args:
            conversation_id: Identifier of the conversation whose request completed.
        """
        with self._active_lock:
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
            signature = self._snapshot_signature(snapshot_path) if self.read_only else None
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
                if self.read_only:
                    self._snapshot_signatures[conversation_id] = signature
            return session

    def _session_snapshot_path(self, record: dict[str, Any]) -> Path:
        return self._session_dir(record) / "interactive-session.json"

    def persist(self) -> None:
        """Atomically write ``conversations.json`` and dirty session snapshots to disk."""
        if not self.persist_sessions:
            return
        with self.lock:
            pairs = [
                (record, self._sessions[record["id"]])
                for record in self._records
                if record["id"] in self._sessions
            ]
        errors = {}
        for record, session in pairs:
            try:
                revision = session.idle_persistence_revision()
                snapshot_path = self._session_snapshot_path(record)
                if (revision is not None and self._saved_idle_revisions.get(record["id"]) == revision
                        and snapshot_path.is_file()):
                    continue
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = snapshot_path.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(session.export_persistent_state(), ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(snapshot_path)
                if revision is not None:
                    self._saved_idle_revisions[record["id"]] = revision
                else:
                    self._saved_idle_revisions.pop(record["id"], None)
            except Exception as exc:
                errors[record["id"]] = exc
                logging.getLogger(__name__).warning("Unable to persist conversation %s: %s", record["id"], type(exc).__name__)
        with self.lock:
            self._persistence_errors = errors
        if errors:
            raise RuntimeError(f"Unable to persist {len(errors)} conversation(s)") from next(iter(errors.values()))

    def _persistence_loop(self) -> None:
        while not self._persistence_stop.wait(self.persistence_interval):
            try:
                self.persist()
            except Exception:
                # Per-conversation errors are recorded; unrelated sessions remain usable.
                logging.getLogger(__name__).warning("Some conversation snapshots could not be saved")

    def _visible(self, record: dict[str, Any], client_id: str) -> bool:
        return not record["archived"] and (
            not self.isolate_users or record["owner_id"] == client_id
        )

    def _owned(self, record: dict[str, Any], client_id: str) -> bool:
        return not self.isolate_users or record["owner_id"] == client_id

    def resolve(
        self,
        client_id: str,
        selected_id: str | None,
        *,
        materialize_reason: str | None = None,
        load_session: bool = True,
    ) -> tuple[dict[str, Any], InteractiveSession | None]:
        """Resolve the active conversation record and session for a client request.

        Args:
            client_id: Browser visitor identifier from the session cookie.
            selected_id: Conversation ID requested via header or query parameter.
            materialize_reason: If provided, promote a temporary session to durable storage
                with this reason string.
            load_session: Whether to instantiate or load the :class:`InteractiveSession`.

        Returns:
            tuple[dict[str, Any], InteractiveSession | None]: Pair of
                ``(conversation_record, interactive_session)``.
        """
        self._refresh_read_only()
        with self.lock:
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
        return record, self._session_for(record) if load_session else None

    def list(self, client_id: str, selected_id: str | None = None) -> dict[str, Any]:
        """Return the visible conversation list and active selection for ``client_id``.

        Args:
            client_id: Browser visitor identifier.
            selected_id: Optional currently selected conversation ID.

        Returns:
            dict[str, Any]: Dictionary containing ``conversations``, ``selected``,
                ``read_only``, and ``persistence_warning``.
        """
        self._refresh_read_only()
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
                "persistence_warning": selected_id in self._persistence_errors,
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
        """Promote a transient in-memory conversation to persistent storage on disk.

        Args:
            client_id: Browser visitor identifier owning the conversation.
            conversation_id: Identifier of the conversation to persist.
            reason: Event label explaining why the conversation became durable.

        Returns:
            tuple[dict[str, Any], InteractiveSession]: Durable conversation record and its session.
        """
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
        """Create a new transient conversation for ``client_id`` without writing empty directories to disk.

        Args:
            client_id: Browser visitor identifier.
            name: Optional initial display name for the conversation.

        Returns:
            dict[str, Any]: Newly created conversation metadata record.
        """
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
        """Select an existing or transient conversation for ``client_id``.

        Args:
            client_id: Browser visitor identifier.
            conversation_id: Conversation identifier to select.

        Returns:
            dict[str, Any]: Selected conversation metadata record.
        """
        self._refresh_read_only()
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
        """Update a conversation's display name in ``conversations.json`` without moving its workspace path.

        Args:
            client_id: Browser visitor identifier.
            conversation_id: Identifier of the conversation to rename.
            name: New non-empty display name (up to 120 characters).

        Returns:
            dict[str, Any]: Updated conversation metadata record.
        """
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
        """Archive (soft-delete) a conversation and return the next selected conversation.

        Args:
            client_id: Browser visitor identifier.
            conversation_id: Identifier of the conversation to archive.
            selected_id: Currently active conversation ID in the client.

        Returns:
            tuple[dict[str, Any], dict[str, Any]]: Pair of ``(archived_record, next_selected_record)``.
        """
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
        """Package a conversation's workspace and session snapshot (excluding ``.env``) into a temporary ZIP file.

        Args:
            client_id: Browser visitor identifier.
            conversation_id: Identifier of the conversation to export.

        Returns:
            tuple[Path, str]: Pair of ``(zip_file_path, download_filename)``.
        """
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
        """Stop the background persistence thread and flush any pending conversation state to disk."""
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
    """Register conversation management middleware and REST endpoints on ``app``.

    Args:
        app: FastAPI application instance.
        registry: Active :class:`ConversationRegistry` instance.
    """

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
        public = path in {"/", "/viewer", "/api/version", "/health"} or path.startswith("/static/")
        selected_id = request.headers.get(CONVERSATION_HEADER) or request.query_params.get(CONVERSATION_QUERY)
        keys = ("client:" + client_id,) + (("conversation:" + selected_id,) if selected_id else ())
        work_token = request_work_keys.set(keys)
        mutation_token = request_mutating.set(request.method not in {"GET", "HEAD", "OPTIONS"})
        request.state.client_id = client_id
        try:
            if public:
                response = await call_next(request)
            else:
                before_reason, after_reason = persistence_timing(request)
                # Listing/creating/selecting chats must not restore a broken current snapshot.
                metadata_only = path == "/api/conversations" or (
                    path.startswith("/api/conversations/") and path.endswith("/select")
                )
                record, session = await app.state.work_pool.run(
                    registry.resolve, client_id, selected_id,
                    materialize_reason=before_reason, load_session=not metadata_only,
                )
                request_work_keys.set(("client:" + client_id, "conversation:" + record["id"]))
                request.state.conversation_id = record["id"]
                registry.acquire(record["id"])
                token = registry.session_proxy.bind(session)
                lease_token = request_session_lease.set((registry, record["id"]))
                try:
                    response = await call_next(request)
                    if after_reason is not None and response.status_code < 400:
                        await app.state.work_pool.run(registry.materialize, client_id, record["id"], after_reason)
                finally:
                    if session is not None and request.method not in {"GET", "HEAD", "OPTIONS"}:
                        session._persistence_generation = getattr(session, "_persistence_generation", 0) + 1
                    registry.session_proxy.reset(token)
                    request_session_lease.reset(lease_token)
                    await run_in_threadpool(registry.release, record["id"])
            response.set_cookie(CLIENT_COOKIE, client_id, httponly=True, samesite="lax", max_age=31536000)
            return response
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        finally:
            request_work_keys.reset(work_token)
            request_mutating.reset(mutation_token)

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
