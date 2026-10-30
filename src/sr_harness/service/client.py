"""Remote implementation of HarnessService using its versioned HTTP contract."""

from __future__ import annotations
import json
from pathlib import Path
from urllib.parse import quote

import httpx

from .base import Download, HarnessService, ServiceError


class HttpHarnessService(HarnessService):
    def __init__(self, base_url: str, token: str, *, transport=None):
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=35,
            transport=transport,
            trust_env=False,
        )
        self.routes = {
            name: (method, path)
            for method, path, name, _ in json.loads(
                Path(__file__).with_name("routes.json").read_text(encoding="utf-8")
            )
        }

    def _json(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        if response.is_error:
            raise ServiceError(
                response.status_code, "Remote Harness operation failed", code="remote_error"
            )
        return response.json() if response.status_code != 204 else None

    def create(self, *, tags, idempotency_key):
        return self._json(
            "POST", "/v1/sessions", json={"tags": tags, "idempotency_key": idempotency_key}
        )

    def list_sessions(self, tags=None):
        values = self._json(
            "GET",
            "/v1/sessions",
            params={"user_ref": tags["user_ref"]} if tags and "user_ref" in tags else {},
        )["sessions"]
        return [r for r in values if all(r["tags"].get(k) == v for k, v in (tags or {}).items())]

    def update(self, session_id, *, tags=None, archived=None):
        return self._json(
            "PATCH",
            f"/v1/sessions/{quote(session_id, safe='')}",
            json={k: v for k, v in {"tags": tags, "archived": archived}.items() if v is not None},
        )

    def invoke(self, session_id, operation, parameters, *, idempotency_key=None):
        extra = {
            "control_command": ("POST", "/control/command"),
            "candidates": ("GET", "/candidates"),
            "control_status": ("GET", "/control/status"),
            "control_events": ("GET", "/control/events"),
            "records": ("GET", "/records"),
            "record": ("GET", "/records/{node_id}"),
            "operation_status": ("GET", "/operations/{operation_id}"),
            "event_download": ("GET", "/control/events/{sequence}"),
        }
        if operation in extra:
            method, path = extra[operation]
        elif operation in self.routes:
            method, path = self.routes[operation]
            path = path.removeprefix("/api")
            if path.startswith("/session"):
                path = path.removeprefix("/session")
        else:
            raise ServiceError(404, "Unknown operation")
        parameters = dict(parameters)
        if operation == "event_download":
            role = parameters.pop("role", "search")
            prefixes = {
                "search": "/control",
                "data": "/data/agent",
                "evaluator": "/evaluator/agent",
            }
            if role not in prefixes:
                raise ServiceError(422, "Unknown agent role")
            path = f"{prefixes[role]}/events/{int(parameters.pop('sequence'))}"
        if operation == "record":
            path = path.replace("{node_id}", quote(parameters.pop("node_id"), safe=""))
        elif operation == "operation_status":
            path = path.replace("{operation_id}", quote(parameters.pop("operation_id"), safe=""))
        kwargs = {"headers": {"Idempotency-Key": idempotency_key}} if idempotency_key else {}
        kwargs["params" if method in {"GET", "DELETE"} else "json"] = parameters.get(
            "payload", parameters
        )
        return self._json(method, f"/v1/sessions/{quote(session_id, safe='')}{path}", **kwargs)

    def credentials(self, session_id, role, configuration):
        self._json(
            "PUT",
            f"/v1/sessions/{quote(session_id, safe='')}/credentials/{quote(role, safe='')}",
            json=configuration,
        )

    def upload(self, session_id, path, stream):
        return self._json(
            "PUT",
            f"/v1/sessions/{quote(session_id, safe='')}/workspace/upload",
            params={"path": path},
            content=iter(lambda: stream.read(1024 * 1024), b""),
        )

    def export(self, session_id):
        request = self.client.build_request(
            "GET", f"/v1/sessions/{quote(session_id, safe='')}/export"
        )
        response = self.client.send(request, stream=True)
        if response.is_error:
            response.close()
            raise ServiceError(response.status_code, "Export failed")
        return Download(
            response.iter_bytes(), f"{session_id}.zip", "application/zip", response.close
        )

    def close(self):
        self.client.close()
