# ASTRAL decoupled deployment

Only Next.js is public. Harness has no published port, database credentials, browser cookies,
or knowledge of user passwords. Its service token is a deployment credential, not a user token.
Use a reverse proxy with HTTPS in production; set APP_ORIGIN to the public origin and COOKIE_SECURE=true.

## Compose (PostgreSQL)

Set DB_PASSWORD, HARNESS_SERVICE_TOKEN (at least 24 random characters), and
CREDENTIAL_MASTER_KEY (32 random bytes encoded as base64). Do not commit their values.

```sh
docker compose up --build -d
docker compose exec -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD='a-long-unique-password' web npm run admin:create
```

The initial registration mode is open. The first registered user is always an ordinary user.
An administrator can switch to invitation-only or administrator-created accounts in the UI.
Invitations expire after seven days and are consumed atomically. Password changes and account
disabling revoke existing login sessions. No email provider is required.

Volumes `harness-data` and `web-database` are separate. Historical Python WebUI directories
are neither mounted nor migrated. Back up both volumes and the credential master key.
Losing the master key requires users/administrators to replace their stored API keys.

## Local development (SQLite)

Harness scientific file access and sandbox execution require Linux. Use Linux/WSL2 or Docker
for the Harness; Web development and transport-only tests also work on Windows.

```sh
pip install -e '.[dev]'
export HARNESS_SERVICE_TOKEN='replace-with-a-random-service-token'
astral serve --root ./harness-data --host 127.0.0.1 --port 8000
cd web
npm ci
# Copy .env.example to .env.local, set the token, encryption key and origin.
npm run db:migrate
npm run dev
```

Scripts load .env.local and .env using Next.js environment loading. Existing shell variables
take precedence. Run the admin creation command with temporary ADMIN_USERNAME/ADMIN_PASSWORD.

## MySQL and PostgreSQL outside Compose

Set DB_DIALECT=mysql and DATABASE_URL=mysql://user:password@host:3306/astral,
or DB_DIALECT=postgresql and DATABASE_URL=postgresql://user:password@host:5432/astral.
Create an empty database and run `npm run db:migrate` before starting Web. SQLite uses
DB_DIALECT=sqlite and a libsql file URL. Dialect-specific migrations represent the same logical
schema; switching an existing database's dialect does not migrate its records.

The ORM repository stores typed entities in a versioned envelope. Unique database keys enforce
usernames and token uniqueness; transactions and compare-and-swap protect invitation consumption
and contested updates. Run the repository integration suite against all three supported drivers.

## Contracts and validation

```sh
python scripts/export_harness_openapi.py
cd web
npm run api:generate
npm run typecheck
npm test
npm run build
npm run test:e2e
```

For Windows development, run the scientific sandbox tests in WSL2 with Docker.
The helper copies source onto the container's native Linux filesystem before
dropping to the application UID; do not run Landlock tests on a Windows bind mount.
The optional playground package and retired deployment tests are excluded.

```sh
docker build -t astral-harness:decoupling-test .
docker build -t astral-web:decoupling-test web
docker run --rm --user 0 -v "$PWD:/repo:ro" -w /repo --entrypoint python astral-harness:decoupling-test scripts/test_linux_container.py
python3 scripts/verify_databases.py
python3 scripts/verify_compose.py
```

These verification scripts create uniquely named test resources and remove only
their own containers, networks and volumes. Compose verification binds a temporary
loopback port and covers accounts, registration, credential encryption, ownership,
streamed upload/download, export and archive against the real production services.

The Harness starts long-running work asynchronously. A 504 does not cancel a thread; retain
the command's idempotency key and inspect state before retrying. Agent concurrency defaults to
8 globally and 2 per `user_ref`, including paused tasks. Tags are correlation data only;
Next.js authorizes every access, including file transfer, events and exports.

Model configuration selects a complete endpoint/key/model pair. Personal failures never retry
using a shared account. Secrets are encrypted in the Web database, sent only over the trusted
internal HTTP connection, held in Harness memory, and excluded from checkpoints and exports.
For a cross-host deployment, protect internal HTTP with TLS before exposing the service network.
Run one Harness process per data root; multi-worker or multi-node scheduling is outside this release.
