import { expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";

it("runs the equivalent repository contract on the configured database", async () => {
  const dialect = process.env.INTEGRATION_DIALECT || "sqlite";
  process.env.DB_DIALECT = dialect;
  process.env.DATABASE_URL =
    process.env.INTEGRATION_DATABASE_URL || "file:./test-repository.db";
  const ddl = await readFile(`migrations/${dialect}/0001.sql`, "utf8");
  if (dialect === "sqlite") {
    const { createClient } = await import("@libsql/client");
    const client = createClient({ url: process.env.DATABASE_URL });
    await client.executeMultiple(ddl);
    client.close();
  } else if (dialect === "postgresql") {
    const { Pool } = await import("pg");
    const pool = new Pool({ connectionString: process.env.DATABASE_URL });
    await pool.query(ddl);
    await pool.end();
  } else {
    const mysql = await import("mysql2/promise");
    const client = await mysql.createConnection(process.env.DATABASE_URL);
    await client.query(ddl);
    await client.end();
  }
  const { repository: repo } = await import("../src/server/db");
  const key = `integration:${randomUUID()}`,
    row = await repo.insert("integration", "owner", { state: "created" }, key);
  expect((await repo.byKey(key))?.id).toBe(row.id);
  await expect(repo.insert("integration", "other", {}, key)).rejects.toThrow();
  await repo.update(row, { state: "updated" });
  await expect(repo.update(row, { state: "stale" })).rejects.toThrow();
  expect((await repo.get<{ state: string }>(row.id))?.data.state).toBe(
    "updated",
  );
  await expect(
    repo.transaction(async (tx) => {
      await tx.insert("integration", "", {}, key + ":rollback");
      throw new Error("rollback");
    }),
  ).rejects.toThrow();
  expect(await repo.byKey(key + ":rollback")).toBeUndefined();
  await repo.remove(row.id);
});
