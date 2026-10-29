"""Verify the real production stack using a disposable, loopback-only Compose project."""

import http.cookiejar
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    project = "astral-stack-test-" + uuid.uuid4().hex[:10]
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env = dict(
        os.environ,
        WEB_PORT=str(port),
        APP_ORIGIN=origin,
        COOKIE_SECURE="false",
        DB_PASSWORD=secrets.token_hex(16),
        HARNESS_SERVICE_TOKEN=secrets.token_hex(32),
        CREDENTIAL_MASTER_KEY=__import__("base64").b64encode(secrets.token_bytes(32)).decode(),
    )
    with tempfile.TemporaryDirectory(prefix="astral-compose-test-") as temporary:
        override = Path(temporary) / "override.yaml"
        override.write_text(f"""services:
  web:
    image: astral-web:decoupling-test
    ports: !override
      - 127.0.0.1:{port}:3000
  harness:
    image: astral-harness:decoupling-test
""")
        command = [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(ROOT / "compose.yaml"),
            "-f",
            str(override),
        ]

        def compose(*args, check=True):
            return subprocess.run(
                [*command, *args],
                env=env,
                text=True,
                check=check,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        def client():
            return urllib.request.build_opener(
                urllib.request.ProxyHandler({}),
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            )

        def request(opener, path, method="GET", payload=None, raw=None):
            data = (
                raw
                if raw is not None
                else json.dumps(payload).encode()
                if payload is not None
                else None
            )
            headers = {
                "Origin": origin,
                "Content-Type": "application/json",
                "Idempotency-Key": uuid.uuid4().hex,
            }
            req = urllib.request.Request(
                origin + "/api/" + path, data=data, method=method, headers=headers
            )
            try:
                response = opener.open(req, timeout=45)
            except urllib.error.HTTPError as error:
                response = error
            content = response.read()
            return response.status, json.loads(content) if "json" in response.headers.get(
                "Content-Type", ""
            ) else content

        try:
            print("Starting isolated production stack", flush=True)
            startup = compose(
                "up", "--no-build", "-d", "--wait", "--wait-timeout", "180", check=False
            )
            if startup.returncode:
                print(startup.stdout, startup.stderr)
                print(compose("logs", "--tail", "30", check=False).stdout)
                raise RuntimeError("Compose stack did not become healthy")
            password = "test-password-" + secrets.token_hex(12)
            compose(
                "exec",
                "-T",
                "-e",
                "ADMIN_USERNAME=admin",
                "-e",
                "ADMIN_PASSWORD=" + password,
                "web",
                "npm",
                "run",
                "admin:create",
            )
            admin, first, second, invited = client(), client(), client(), client()
            assert (
                request(admin, "auth/login", "POST", {"username": "admin", "password": password})[0]
                == 200
            )
            assert request(admin, "admin/registration", "PUT", {"mode": "invite"})[0] == 200
            assert (
                request(
                    first, "auth/register", "POST", {"username": "blocked", "password": password}
                )[0]
                == 403
            )
            status, invitation = request(admin, "admin/invitations", "POST", {})
            assert status == 201
            assert (
                request(
                    invited,
                    "auth/register",
                    "POST",
                    {
                        "username": "invited",
                        "password": password,
                        "invitation": invitation["token"],
                    },
                )[0]
                == 201
            )
            assert (
                request(
                    first,
                    "auth/register",
                    "POST",
                    {"username": "reused", "password": password, "invitation": invitation["token"]},
                )[0]
                == 403
            )
            assert request(admin, "admin/registration", "PUT", {"mode": "admin"})[0] == 200
            status, account = request(
                admin, "admin/users", "POST", {"username": "managed", "password": password}
            )
            assert status == 201
            assert (
                request(
                    first, "auth/register", "POST", {"username": "closed", "password": password}
                )[0]
                == 403
            )
            assert (
                request(
                    invited, "auth/login", "POST", {"username": "managed", "password": password}
                )[0]
                == 200
            )
            assert (
                request(
                    admin,
                    "admin/users/" + account["id"],
                    "PATCH",
                    {"password": password + "-reset"},
                )[0]
                == 200
            )
            assert request(invited, "auth/me")[0] == 401
            assert request(admin, "admin/registration", "PUT", {"mode": "open"})[0] == 200
            for opener, username in [(first, "first-user"), (second, "second-user")]:
                assert (
                    request(
                        opener,
                        "auth/register",
                        "POST",
                        {"username": username, "password": password},
                    )[0]
                    == 201
                )
                assert (
                    request(
                        opener, "auth/login", "POST", {"username": username, "password": password}
                    )[0]
                    == 200
                )
                assert request(opener, "auth/me")[1]["role"] == "user"
            private_key = "test-private-key-" + secrets.token_hex(16)
            assert (
                request(
                    first,
                    "models",
                    "POST",
                    {
                        "name": "Personal",
                        "provider": "compatible",
                        "endpoint": "http://mock.invalid/v1",
                        "model": "mock",
                        "api_key": private_key,
                        "isDefault": True,
                    },
                )[0]
                == 201
            )
            assert private_key not in json.dumps(request(first, "models")[1])
            persisted = compose(
                "exec",
                "-T",
                "database",
                "psql",
                "-U",
                "astral",
                "-d",
                "astral",
                "-Atc",
                "SELECT payload FROM entities WHERE kind='model'",
            ).stdout
            assert private_key not in persisted and '"secret"' in persisted
            status, conversation = request(
                first, "conversations", "POST", {"name": "Production study"}
            )
            assert status == 201
            cid = conversation["id"]
            assert request(first, f"conversations/{cid}/harness")[0] == 200
            assert request(second, f"conversations/{cid}/harness")[0] == 404
            assert request(first, "admin/users")[0] == 403
            content = b"x" * (5 * 1024 * 1024)
            assert (
                request(
                    first,
                    f"conversations/{cid}/harness/workspace/upload?path=observations.bin",
                    "PUT",
                    raw=content,
                )[0]
                == 200
            )
            assert (
                request(
                    first, f"conversations/{cid}/harness/workspace/download?path=observations.bin"
                )[1]
                == content
            )
            status, archive = request(first, f"conversations/{cid}/harness/export")
            assert status == 200
            with zipfile.ZipFile(io.BytesIO(archive)) as exported:
                assert "workspace/observations.bin" in exported.namelist()
                assert all(
                    private_key.encode() not in exported.read(name) for name in exported.namelist()
                )
            assert request(first, f"conversations/{cid}", "DELETE")[0] == 200
            assert not request(first, "conversations")[1]["conversations"]
            print(
                "Production Compose: login, all registration modes, reset/revocation, "
                "encrypted model storage, ownership, 5 MiB streaming, export and archive passed",
                flush=True,
            )
        finally:
            compose("down", "-v", "--remove-orphans", check=False)
            print("Removed only this test project's containers, networks and volumes", flush=True)


if __name__ == "__main__":
    main()
