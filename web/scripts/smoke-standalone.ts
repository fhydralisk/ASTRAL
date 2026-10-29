/** Exercise the production Web build against a separately running real Harness API. */
import { spawn, spawnSync } from "node:child_process";
import { once } from "node:events";
import { rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { randomBytes, randomUUID } from "node:crypto";
import assert from "node:assert/strict";

const database = join(tmpdir(), `astral-production-${randomUUID()}.db`);
const webPort = process.env.SMOKE_WEB_PORT || "3106";
const origin = "http://127.0.0.1:" + webPort;
const env: NodeJS.ProcessEnv = {
  ...process.env,
  DB_DIALECT: "sqlite",
  DATABASE_URL: pathToFileURL(database).href,
  APP_ORIGIN: origin,
  COOKIE_SECURE: "false",
  NODE_ENV: "production",
  CREDENTIAL_MASTER_KEY: randomBytes(32).toString("base64"),
  HOSTNAME: "127.0.0.1",
  PORT: webPort,
};
const migration = spawnSync(
  process.execPath,
  ["node_modules/tsx/dist/cli.mjs", "scripts/migrate.ts"],
  { env, encoding: "utf8", windowsHide: true },
);
assert.equal(migration.status, 0, migration.stderr);
const server = spawn(process.execPath, [".next/standalone/server.js"], {
  env,
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
});
let logs = "";
server.stdout.on("data", (data) => {
  logs = (logs + data).slice(-5000);
});
server.stderr.on("data", (data) => {
  logs = (logs + data).slice(-5000);
});
try {
  let ready = false;
  for (let attempt = 0; attempt < 50; attempt++) {
    try {
      if ((await fetch(origin + "/api/health")).ok) {
        ready = true;
        break;
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  assert(ready, logs);
  const page = await fetch(origin),
    html = await page.text();
  assert.equal(page.status, 200);
  const assets = Array.from(
    html.matchAll(/(?:src|href)="(\/_next\/static\/[^" ]+)"/g),
    (match) => match[1],
  );
  assert(assets.length > 0);
  for (const asset of assets)
    assert.equal((await fetch(origin + asset)).status, 200, asset);
  const request = (path: string, method = "GET", cookie = "", data?: unknown) =>
    fetch(origin + "/api/" + path, {
      method,
      headers: {
        origin,
        "content-type": "application/json",
        cookie,
        "idempotency-key": randomUUID(),
      },
      ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    });
  async function account() {
    const username = "smoke-" + randomUUID().slice(0, 8),
      password = "production-smoke-password-123";
    assert.equal(
      (await request("auth/register", "POST", "", { username, password }))
        .status,
      201,
    );
    const login = await request("auth/login", "POST", "", {
      username,
      password,
    });
    assert.equal(login.status, 200);
    return login.headers.get("set-cookie")!.split(";")[0];
  }
  const first = await account(),
    second = await account();
  const created = await request("conversations", "POST", first, {
    name: "Real independent Harness",
  });
  assert.equal(created.status, 201, await created.clone().text());
  const conversation = await created.json();
  const state = await request(
    `conversations/${conversation.id}/harness`,
    "GET",
    first,
  );
  assert.equal(state.status, 200);
  assert.equal((await state.json()).state, "idle");
  assert.equal(
    (await request(`conversations/${conversation.id}/harness`, "GET", second))
      .status,
    404,
  );
  assert.equal((await request("conversations")).status, 401);
  console.log(
    "Production standalone: assets, login, real Harness HTTP and ownership checks passed",
  );
} finally {
  const exit = once(server, "exit");
  if (server.exitCode === null) {
    server.kill();
    await exit;
  }
  for (const suffix of ["", "-wal", "-shm"])
    await rm(database + suffix, { force: true });
}
