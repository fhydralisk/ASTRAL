# ASTRAL Web

Next.js App Router, React and TypeScript. Browser requests terminate at Next.js; only the
server-side Harness client knows the internal service URL and token. User ownership lives in
the Web database. Harness tags correlate execution sessions with users, without authorizing them.

## Run

1. Copy `.env.example` to `.env.local`; configure the service token and a base64 32-byte
   `CREDENTIAL_MASTER_KEY`. Use a distinct master key from the Harness service token.
2. Start the Python API separately with `astral serve --root ./harness-data` on Linux.
3. Run `npm ci`, `npm run db:migrate`, then `npm run dev`.
4. Create an administrator with `ADMIN_USERNAME` and `ADMIN_PASSWORD` in the command environment
   using `npm run admin:create`. Public registration always creates ordinary users.

SQLite is the local default. Set DB_DIALECT to mysql or postgresql with the corresponding
DATABASE_URL to use another driver. Apply that dialect's migration before starting the app.
The root Compose stack defaults to PostgreSQL. See [deployment](../deploy/decoupled/README.md).

## Boundaries

- `src/app` and `src/components`: React workbench, account and administration UI.
- `src/components/research`: original `main` workbench layout and interaction controllers,
  mounted and disposed by React. See its README for the migration boundary and reference commit.
- `src/server`: authentication, ownership, encrypted model storage, ORM repository and HTTP client.
- `src/lib/harness-schema.d.ts`: generated from the checked-in OpenAPI contract.
- `src/lib/scientific-routes.ts`: generated allowlist; credentials and user tags have no browser proxy.
- `migrations`: equivalent SQLite, MySQL and PostgreSQL schemas.

Shared defaults and personal model configurations are complete endpoint/key/model pairs. They
are never mixed, and a failed personal configuration never retries using a shared paid account.
Secrets are encrypted in the Web database, never returned by read APIs, and supplied only to the
selected Harness agent at an execution boundary. HTTPS origins always receive Secure cookies.

## Verify

```sh
npm run api:generate
npm run typecheck
npm test
npm run build
npm run test:e2e
```

`npm run build` also prepares public/static assets for `.next/standalone/server.js`.
The browser suite uses the real Next.js backend and a test-only remote Harness double;
Python service tests independently exercise the real Harness HTTP adapter. Linux CI additionally
runs the actual scientific workspace/search workflow. MySQL/PostgreSQL integration jobs use
real database service containers. No test requires a paid model API.

The restored workbench is based on `origin/main` at `1ee6cff`, including observational
evaluators/tools/skills and the large-event timeline fix. Browser tests compare the original
and migrated panel geometry at desktop and mobile widths and exercise the original three-stage
workflow. Account/model management lives in a dialog; each Agent's original settings surface
selects complete encrypted model profiles instead of handling raw provider credentials.
