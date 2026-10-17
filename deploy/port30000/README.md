# Port 30000 container deployment

Run all commands from the repository root. The backend defaults to the published
`yumeoww/sr-harness:1.0.6` image. Set `SRH_IMAGE` to override it. For a local build,
set `SRH_IMAGE=sr-harness:port30000` for both `build sr-harness` and `up` commands.

```bash
docker compose --env-file .env -f deploy/port30000/compose.yaml pull sr-harness
docker compose --env-file .env -f deploy/port30000/compose.yaml build web-gateway openrouter-gateway egress-proxy
docker compose --env-file .env -f deploy/port30000/compose.yaml up -d
docker compose -f deploy/port30000/compose.yaml ps
docker compose -f deploy/port30000/compose.yaml logs -f --tail=100
```

The SRHarness container can write only to `logs/port30000` and its temporary filesystem. It does
not mount the repository, the Docker socket, or other host paths. Its root filesystem is read-only,
all Linux capabilities are dropped, privilege escalation is disabled, and its Docker network has
no direct Internet route. Public HTTP and HTTPS access goes through a separate egress gateway that
rejects loopback, private, link-local, reserved, and cloud-metadata destinations. The gateway also
limits global and per-destination concurrency, connection rate, and per-connection bandwidth.
The deployment gateway is not shown as the editable WebUI proxy. A proxy explicitly configured in
a conversation is treated as an upstream HTTP(S) proxy and is itself reached through the gateway;
without one, the gateway connects to the public destination directly.

Port 30000 is published by a separate, read-only Nginx ingress container. The SRHarness container
is attached only to the internal network; the ingress container forwards browser traffic to it.

The `/tmp` filesystem is ephemeral. It remains executable because optional scientific backends
such as Julia may install or execute runtime files there; it is still isolated inside the
container and mounted with `nosuid,nodev`.

Stop or update the service with:

```bash
docker compose -f deploy/port30000/compose.yaml down
docker compose --env-file .env -f deploy/port30000/compose.yaml pull sr-harness
docker compose --env-file .env -f deploy/port30000/compose.yaml up -d --no-build
```

The real OpenRouter API key is supplied only to the separate gateway container. Its startup script
removes the key from the running process environment after generating an ephemeral proxy config.
SRHarness receives a non-secret placeholder and can reach OpenRouter only through that gateway.
This prevents scripts in the SRHarness container from reading or exfiltrating the upstream key, but
it cannot prevent them from abusing the gateway to incur model charges. Use a dedicated, low-limit,
revocable API key for a public deployment and monitor its spend limit.

Internet-enabled tools can send workspace or conversation data to arbitrary public services and
download untrusted code. The gateway limits access to ports 80 and 443, blocks private networks,
and places conservative resource ceilings on outbound traffic, but it does not provide domain
allow-listing or content inspection. Do not put sensitive data in this public demo.


## HTTP fault containment

Synchronous API work, session restoration, and response encoding use a bounded worker pool:
16 tasks globally and 4 per browser identity or selected conversation. There is no unbounded
work queue. Saturated requests return 429/503 with `Retry-After`; a task taking more than
30 seconds returns 504. Timed-out or disconnected requests retain their capacity until the
underlying thread actually exits. A timed-out mutation may still complete: inspect its state
before retrying. This timeout applies to HTTP work, not the lifetime of a background Agent run.

JSON request bodies are limited to 4 MiB (including chunked bodies). File upload keeps its
separate streaming 256 MiB limit. JSON responses have an 8 MiB, 200,000-node, 64-level budget;
oversized responses return 413 without truncating stored data. Event pages shrink to fit the
budget without advancing past omitted events. A single oversized event requires export.
File transfers are streamed rather than subjected to the JSON response limit.

The home page, version endpoint, and asynchronous backend `/health` bypass the request pool.
Conversation listing does not restore the selected session. Snapshot write failures are tracked
per conversation and do not prevent other snapshots or reads; the list API exposes a
`persistence_warning` for the selected conversation. Unchanged idle snapshots are not rewritten;
sessions with a live Agent thread retain periodic saves. Ingress connection/read timeouts are
5/65 seconds; SSE sends heartbeat comments while idle.

These measures contain slow HTTP work and serialization failures. They do not provide a separate
OS memory/GIL boundary for every Agent: the Web process and Agent orchestration still share a
process, and container-wide OOM/native crashes remain possible. Existing untrusted tool workers
retain their subprocess sandbox and resource limits. Full per-session process supervision is a
separate architectural change; do not treat HTTP timeouts as task termination or auto-restart.
