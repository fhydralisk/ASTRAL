import nextEnv from "@next/env";
nextEnv.loadEnvConfig(process.cwd());
import { readFile } from "node:fs/promises";
import { createClient } from "@libsql/client";
import { Pool } from "pg";
import mysql from "mysql2/promise";
const dialect = process.env.DB_DIALECT || "sqlite";
const source = await readFile(
  new URL(`../migrations/${dialect}/0001.sql`, import.meta.url),
  "utf8",
);
if (dialect === "sqlite") {
  const client = createClient({
    url: process.env.DATABASE_URL || "file:./astral.db",
  });
  await client.executeMultiple(source);
  client.close();
} else if (dialect === "postgresql") {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });
  await pool.query(source);
  await pool.end();
} else if (dialect === "mysql") {
  const client = await mysql.createConnection(process.env.DATABASE_URL!);
  await client.query(source);
  await client.end();
} else throw new Error("Unsupported database dialect");
console.log("Database schema ready:", dialect);
