import { beforeAll, describe, expect, it, vi } from "vitest";
import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import { createClient } from "@libsql/client";

const jar = new Map<string, string>();
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (k: string) => (jar.has(k) ? { value: jar.get(k) } : undefined),
    set: (k: string, v: string) => jar.set(k, v),
    delete: (k: string) => jar.delete(k),
  }),
}));
beforeAll(async () => {
  process.env.DB_DIALECT = "sqlite";
  process.env.DATABASE_URL = "file:./test-backend.db";
  process.env.CREDENTIAL_MASTER_KEY = randomBytes(32).toString("base64");
  process.env.APP_ORIGIN = "http://localhost:3000";
  process.env.HARNESS_SERVICE_TOKEN = "unit-test-internal-token-12345678";
  const client = createClient({ url: process.env.DATABASE_URL });
  await client.execute("DROP TABLE IF EXISTS entities");
  await client.executeMultiple(
    await readFile("migrations/sqlite/0001.sql", "utf8"),
  );
  client.close();
});
describe("accounts, ownership and credentials", () => {
  it("ordinary registration never grants admin; authentication is revocable", async () => {
    const s = await import("../src/server/security");
    const user = await s.register("ordinary", "test-password-123");
    expect(user.data.role).toBe("user");
    await s.login("ordinary", "test-password-123");
    expect((await s.requireUser()).id).toBe(user.id);
    await expect(s.requireUser(true)).rejects.toMatchObject({ status: 403 });
    await s.revoke(user.id);
    await expect(s.requireUser()).rejects.toMatchObject({ status: 401 });
  });
  it("supports closed and one-time invitation registration modes", async () => {
    const s = await import("../src/server/security"),
      { repository: repo } = await import("../src/server/db");
    const setting = await repo.insert(
      "setting",
      "",
      { mode: "admin" },
      "setting:registration",
    );
    await expect(
      s.register("closed-user", "test-password-123"),
    ).rejects.toMatchObject({ status: 403 });
    await repo.update(setting, { mode: "invite" });
    const token = await s.invitation("admin");
    await s.register("invited-user", "test-password-123", token);
    await expect(
      s.register("second-user", "test-password-123", token),
    ).rejects.toMatchObject({ status: 403 });
  });
  it("enforces ownership even for an administrator", async () => {
    const { repository: repo } = await import("../src/server/db"),
      { owned } = await import("../src/server/conversations");
    const row = await repo.insert("conversation", "owner", { name: "private" });
    await expect(
      owned({ id: "admin", role: "admin", username: "admin" }, row.id),
    ).rejects.toMatchObject({ status: 404 });
    expect(
      (await owned({ id: "owner", role: "user", username: "owner" }, row.id))
        .id,
    ).toBe(row.id);
  });
  it("encrypts keys, authenticates ciphertext and never mixes personal/shared pairs", async () => {
    const s = await import("../src/server/security"),
      m = await import("../src/server/models"),
      { repository: repo } = await import("../src/server/db");
    const encrypted = s.encrypt("private-api-key");
    expect(encrypted).not.toContain("private-api-key");
    expect(s.decrypt(encrypted)).toBe("private-api-key");
    const tampered = Buffer.from(encrypted, "base64");
    tampered[15] ^= 1;
    expect(() => s.decrypt(tampered.toString("base64"))).toThrow();
    const admin = { id: "admin", username: "admin", role: "admin" as const },
      user = { id: "model-user", username: "user", role: "user" as const };
    await m.saveModel(admin, {
      name: "shared",
      provider: "compatible",
      endpoint: "https://shared.test/v1",
      model: "shared",
      api_key: "shared-secret",
      shared: true,
      isDefault: true,
    });
    const personal = await m.saveModel(user, {
      name: "personal",
      provider: "compatible",
      endpoint: "https://personal.test/v1",
      model: "personal",
      api_key: "personal-secret",
      isDefault: true,
    });
    expect(JSON.stringify(await m.visibleModels(user))).not.toContain(
      "personal-secret",
    );
    expect(await m.resolveModel(user)).toMatchObject({
      api_key: "personal-secret",
      endpoint: "https://personal.test/v1",
    });
    await repo.remove(personal.id);
    await expect(m.resolveModel(user, personal.id)).rejects.toMatchObject({
      status: 409,
    });
    expect(await m.resolveModel(user)).toMatchObject({
      api_key: "shared-secret",
      endpoint: "https://shared.test/v1",
    });
    await expect(
      m.saveModel(user, {
        name: "bad",
        provider: "compatible",
        model: "m",
        api_key: "secret",
        shared: true,
      }),
    ).rejects.toMatchObject({ status: 403 });
  });
  it("rejects cross-origin writes and rate limits authentication", async () => {
    const { checkOrigin, rateLimit } = await import("../src/server/security");
    expect(() =>
      checkOrigin(
        new Request("http://localhost:3000/api/models", {
          method: "POST",
          headers: { origin: "https://evil.test" },
        }),
      ),
    ).toThrow();
    rateLimit("test-key", 1);
    expect(() => rateLimit("test-key", 1)).toThrow();
  });
  it("routes administrator account actions through authorization and revokes old logins", async () => {
    const s = await import("../src/server/security");
    const { GET, POST, PATCH } = await import("../src/app/api/[...path]/route");
    const { NextRequest } = await import("next/server");
    const invoke = (
      fn: typeof POST,
      path: string,
      method = "POST",
      data?: unknown,
    ) =>
      fn(
        new NextRequest("http://localhost:3000/api/" + path, {
          method,
          headers: {
            origin: "http://localhost:3000",
            "content-type": "application/json",
          },
          ...(data ? { body: JSON.stringify(data) } : {}),
        }),
        { params: Promise.resolve({ path: path.split("/") }) },
      );
    await s.createUser("api-admin", "administrator-password-123", "admin");
    await s.login("api-admin", "administrator-password-123");
    const adminToken = jar.get("astral_session")!;
    const created = await invoke(POST, "admin/users", "POST", {
      username: "api-user",
      password: "ordinary-password-123",
    });
    expect(created.status).toBe(201);
    const id = (await created.json()).id;
    await s.login("api-user", "ordinary-password-123");
    const oldToken = jar.get("astral_session")!;
    expect((await invoke(GET, "admin/users", "GET")).status).toBe(403);
    jar.set("astral_session", adminToken);
    expect(
      (
        await invoke(PATCH, "admin/users/" + id, "PATCH", {
          password: "replacement-password-123",
        })
      ).status,
    ).toBe(200);
    jar.set("astral_session", oldToken);
    await expect(s.requireUser()).rejects.toMatchObject({ status: 401 });
    await expect(
      s.login("api-user", "ordinary-password-123"),
    ).rejects.toMatchObject({ status: 401 });
    await s.login("api-user", "replacement-password-123");
  });
  it("never trusts browser ownership tags or exposes credential endpoints", async () => {
    const { POST, PUT } = await import("../src/app/api/[...path]/route");
    const { NextRequest } = await import("next/server");
    const { requireUser } = await import("../src/server/security");
    const identity = await requireUser();
    const mock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (_url, init) => {
        const payload = JSON.parse(init!.body as string);
        expect(payload.tags.user_ref).toBe(identity.id);
        expect(payload.tags.user_ref).not.toBe("forged-user");
        return new Response(JSON.stringify({ id: "a".repeat(32) }), {
          status: 201,
        });
      });
    try {
      const request = new NextRequest(
        "http://localhost:3000/api/conversations",
        {
          method: "POST",
          headers: {
            origin: "http://localhost:3000",
            "content-type": "application/json",
            "idempotency-key": "ownership-test",
          },
          body: JSON.stringify({
            name: "Owned",
            tags: { user_ref: "forged-user" },
          }),
        },
      );
      const response = await POST(request, {
        params: Promise.resolve({ path: ["conversations"] }),
      });
      expect(response.status).toBe(201);
      const { id } = await response.json();
      const path = ["conversations", id, "harness", "credentials", "search"];
      const forbidden = await PUT(
        new NextRequest("http://localhost:3000/api/" + path.join("/"), {
          method: "PUT",
          headers: { origin: "http://localhost:3000" },
          body: "{}",
        }),
        { params: Promise.resolve({ path }) },
      );
      expect(forbidden.status).toBe(404);
      expect(mock).toHaveBeenCalledTimes(1);
    } finally {
      mock.mockRestore();
    }
  });
});
