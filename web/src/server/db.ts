import { createClient } from "@libsql/client";
import { drizzle as sqliteDrizzle } from "drizzle-orm/libsql";
import { drizzle as pgDrizzle } from "drizzle-orm/node-postgres";
import { drizzle as mysqlDrizzle } from "drizzle-orm/mysql2";
import {
  sqliteTable,
  text as st,
  integer as si,
  index as sx,
} from "drizzle-orm/sqlite-core";
import {
  pgTable,
  text as pt,
  integer as pi,
  index as px,
} from "drizzle-orm/pg-core";
import {
  mysqlTable,
  varchar,
  longtext,
  int,
  index as mx,
} from "drizzle-orm/mysql-core";
import { and, eq } from "drizzle-orm";
import { Pool } from "pg";
import mysql from "mysql2/promise";
import { randomUUID } from "node:crypto";

export type Entity<T = Record<string, unknown>> = {
  id: string;
  kind: string;
  owner: string;
  key: string;
  version: number;
  data: T;
};
// All dialects use the same logical envelope. The unique key enforces usernames and tokens
// atomically in the database; version provides compare-and-swap for contested updates.
const sqliteSchema = sqliteTable(
  "entities",
  {
    id: st("id").primaryKey(),
    kind: st("kind").notNull(),
    owner: st("owner").notNull(),
    key: st("entity_key").notNull().unique(),
    version: si("version").notNull().default(0),
    payload: st("payload").notNull(),
  },
  (t) => [sx("kind_owner").on(t.kind, t.owner)],
);
const pgSchema = pgTable(
  "entities",
  {
    id: pt("id").primaryKey(),
    kind: pt("kind").notNull(),
    owner: pt("owner").notNull(),
    key: pt("entity_key").notNull().unique(),
    version: pi("version").notNull().default(0),
    payload: pt("payload").notNull(),
  },
  (t) => [px("kind_owner").on(t.kind, t.owner)],
);
const mysqlSchema = mysqlTable(
  "entities",
  {
    id: varchar("id", { length: 36 }).primaryKey(),
    kind: varchar("kind", { length: 32 }).notNull(),
    owner: varchar("owner", { length: 64 }).notNull(),
    key: varchar("entity_key", { length: 191 }).notNull().unique(),
    version: int("version").notNull().default(0),
    payload: longtext("payload").notNull(),
  },
  (t) => [mx("kind_owner").on(t.kind, t.owner)],
);
export const dialect = process.env.DB_DIALECT || "sqlite";
if (!["sqlite", "mysql", "postgresql"].includes(dialect))
  throw new Error("Unsupported DB_DIALECT");
// Driver-specific query builder types differ; this is the only dynamic boundary.
// Business code uses the typed repository below, never a driver or SQL string.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let driver: any;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let schema: any;
if (dialect === "sqlite") {
  schema = sqliteSchema;
  driver = sqliteDrizzle(
    createClient({ url: process.env.DATABASE_URL || "file:./astral.db" }),
  );
} else if (dialect === "postgresql") {
  schema = pgSchema;
  driver = pgDrizzle(new Pool({ connectionString: process.env.DATABASE_URL }));
} else {
  schema = mysqlSchema;
  driver = mysqlDrizzle(mysql.createPool(process.env.DATABASE_URL!), {
    mode: "default",
  });
}

export class Repository {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  constructor(private db: any = driver) {}
  private decode<T>(row: Record<string, unknown>): Entity<T> {
    return { ...row, data: JSON.parse(row.payload as string) } as Entity<T>;
  }
  async list<T>(kind: string, owner?: string): Promise<Entity<T>[]> {
    const rows = await this.db
      .select()
      .from(schema)
      .where(
        owner === undefined
          ? eq(schema.kind, kind)
          : and(eq(schema.kind, kind), eq(schema.owner, owner)),
      );
    return rows.map((r: Record<string, unknown>) => this.decode<T>(r));
  }
  async get<T>(id: string): Promise<Entity<T> | undefined> {
    const [row] = await this.db.select().from(schema).where(eq(schema.id, id));
    return row ? this.decode<T>(row) : undefined;
  }
  async byKey<T>(key: string): Promise<Entity<T> | undefined> {
    const [row] = await this.db
      .select()
      .from(schema)
      .where(eq(schema.key, key));
    return row ? this.decode<T>(row) : undefined;
  }
  async insert<T>(
    kind: string,
    owner: string,
    data: T,
    key?: string,
  ): Promise<Entity<T>> {
    const id = randomUUID();
    const entity = {
      id,
      kind,
      owner,
      key: key || `${kind}:${id}`,
      version: 0,
      data,
    };
    await this.db
      .insert(schema)
      .values({
        id,
        kind,
        owner,
        key: entity.key,
        version: 0,
        payload: JSON.stringify(data),
      });
    return entity;
  }
  async update<T>(entity: Entity<T>, data: T): Promise<void> {
    const result = await this.db
      .update(schema)
      .set({ payload: JSON.stringify(data), version: entity.version + 1 })
      .where(and(eq(schema.id, entity.id), eq(schema.version, entity.version)));
    const changes =
      result?.rowsAffected ?? result?.rowCount ?? result?.[0]?.affectedRows;
    if (changes !== 1) throw new Error("Concurrent update; refresh and retry");
  }
  async remove(id: string) {
    await this.db.delete(schema).where(eq(schema.id, id));
  }
  async transaction<T>(fn: (repo: Repository) => Promise<T>): Promise<T> {
    return this.db.transaction((tx: unknown) => fn(new Repository(tx)));
  }
}
export const repository = new Repository();
