import { NextRequest, NextResponse } from "next/server";
import { hash } from "@node-rs/argon2";
import { z } from "zod";
import { repository } from "@/server/db";
import {
  ApiError,
  checkOrigin,
  createUser,
  invitation,
  login,
  logout,
  rateLimit,
  register,
  registrationMode,
  requireUser,
  revoke,
  type User,
} from "@/server/security";
import {
  roles,
  saveModel,
  visibleModels,
  type Model,
  type Role,
} from "@/server/models";
import {
  createConversation,
  ensureHarness,
  owned,
  supplyModel,
  type Conversation,
} from "@/server/conversations";
import { harness, harnessJSON } from "@/server/harness";
import { scientificRoutes } from "@/lib/scientific-routes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const credentials = z.object({
  username: z.string().max(64),
  password: z.string().max(1024),
  invitation: z.string().max(100).optional(),
});
type Context = { params: Promise<{ path: string[] }> };
async function body(request: Request) {
  if (Number(request.headers.get("content-length") || 0) > 4 * 1024 * 1024)
    throw new ApiError(413, "Request too large");
  const reader = request.body?.getReader();
  let size = 0;
  const chunks: Uint8Array[] = [];
  if (reader)
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 4 * 1024 * 1024) {
        await reader.cancel();
        throw new ApiError(413, "Request too large");
      }
      chunks.push(value);
    }
  try {
    return JSON.parse(Buffer.concat(chunks).toString() || "{}");
  } catch {
    throw new ApiError(422, "Invalid JSON");
  }
}
const json = (data: unknown, status = 200) =>
  NextResponse.json(data, { status });
async function audit(userId: string, action: string, target: string) {
  await repository.insert("audit", userId, { action, target, at: Date.now() });
}

async function handler(
  request: NextRequest,
  context: Context,
): Promise<Response> {
  try {
    checkOrigin(request);
    const path = (await context.params).path,
      route = path.join("/"),
      method = request.method;
    if (route === "health" && method === "GET") return json({ status: "ok" });
    if (route === "auth/mode" && method === "GET")
      return json({ mode: await registrationMode() });
    if (
      (route === "auth/login" || route === "auth/register") &&
      method === "POST"
    ) {
      rateLimit(`auth:${route}`, 50);
      const values = credentials.parse(await body(request));
      rateLimit(`account:${values.username.toLowerCase()}`, 10);
      if (route === "auth/register") {
        const user = await register(
          values.username,
          values.password,
          values.invitation,
        );
        await audit(user.id, "register", user.id);
        return json({ ok: true }, 201);
      }
      return json(await login(values.username, values.password));
    }
    const user = await requireUser(path[0] === "admin");
    if (route === "auth/me" && method === "GET") return json(user);
    if (route === "auth/logout" && method === "POST") {
      await logout();
      return json({ ok: true });
    }
    if (route === "admin/registration") {
      if (method === "GET") return json({ mode: await registrationMode() });
      if (method === "PUT") {
        const { mode } = z
          .object({ mode: z.enum(["open", "invite", "admin"]) })
          .parse(await body(request));
        const setting = await repository.byKey<{ mode: string }>(
          "setting:registration",
        );
        if (setting) await repository.update(setting, { mode });
        else
          await repository.insert(
            "setting",
            "",
            { mode },
            "setting:registration",
          );
        await audit(user.id, "registration_mode", mode);
        return json({ mode });
      }
    }
    if (route === "admin/invitations" && method === "POST")
      return json({ token: await invitation(user.id) }, 201);
    if (route === "admin/users") {
      if (method === "GET")
        return json({
          users: (await repository.list<User>("user")).map((u) => ({
            id: u.id,
            username: u.data.username,
            role: u.data.role,
            disabled: u.data.disabled,
          })),
        });
      if (method === "POST") {
        const values = credentials.parse(await body(request));
        const created = await createUser(values.username, values.password);
        await audit(user.id, "create_user", created.id);
        return json({ id: created.id }, 201);
      }
    }
    if (
      path[0] === "admin" &&
      path[1] === "users" &&
      path.length === 3 &&
      method === "PATCH"
    ) {
      const target = await repository.get<User>(path[2]);
      if (!target || target.kind !== "user" || target.data.role === "admin")
        throw new ApiError(
          403,
          "Only ordinary user accounts may be changed here",
        );
      const values = z
        .object({
          password: z.string().min(12).max(1024).optional(),
          disabled: z.boolean().optional(),
        })
        .parse(await body(request));
      await repository.update(target, {
        ...target.data,
        ...(values.password
          ? {
              passwordHash: await hash(values.password, {
                memoryCost: 19456,
                timeCost: 2,
                parallelism: 1,
              }),
            }
          : {}),
        ...(values.disabled === undefined ? {} : { disabled: values.disabled }),
      });
      await revoke(target.id);
      await audit(user.id, "update_user", target.id);
      return json({ ok: true });
    }
    if (route === "models") {
      if (method === "GET") return json({ models: await visibleModels(user) });
      if (method === "POST")
        return json(await saveModel(user, await body(request)), 201);
    }
    if (path[0] === "models" && path.length === 2) {
      if (method === "PUT")
        return json(await saveModel(user, await body(request), path[1]));
      if (method === "DELETE") {
        const model = await repository.get<Model>(path[1]);
        if (
          !model ||
          model.kind !== "model" ||
          (model.owner !== user.id &&
            !(user.role === "admin" && model.data.shared))
        )
          throw new ApiError(404, "Model not found");
        await repository.remove(model.id);
        return json({ ok: true });
      }
    }
    if (route === "conversations") {
      if (method === "GET")
        return json({
          conversations: (
            await repository.list<Conversation>("conversation", user.id)
          )
            .filter((c) => !c.data.archived)
            .map((c) => ({
              id: c.id,
              ...c.data,
              harnessId: undefined,
              creationKey: undefined,
            })),
        });
      if (method === "POST") {
        const values = z
          .object({ name: z.string().max(100).default("Unnamed Conversation") })
          .parse(await body(request));
        const entity = await createConversation(
          user,
          request.headers.get("idempotency-key") || "",
          values.name,
        );
        return json({ id: entity.id, name: entity.data.name }, 201);
      }
    }
    if (path[0] === "conversations" && path.length >= 2) {
      const entity = await owned(user, path[1]);
      if (path.length === 2 && method === "PATCH") {
        const values = z
          .object({
            name: z.string().min(1).max(100).optional(),
            models: z
              .object({
                search: z.string().optional(),
                data: z.string().optional(),
                evaluator: z.string().optional(),
              })
              .optional(),
          })
          .parse(await body(request));
        if (values.models) {
          const visible = await visibleModels(user);
          for (const id of Object.values(values.models))
            if (id && !visible.some((m) => m.id === id))
              throw new ApiError(404, "Model not found");
        }
        await repository.update(entity, { ...entity.data, ...values });
        return json({ ok: true });
      }
      const sid = await ensureHarness(entity);
      if (path.length === 2 && method === "DELETE") {
        await harnessJSON(`/v1/sessions/${sid}`, "PATCH", { archived: true });
        await repository.update(entity, { ...entity.data, archived: true });
        return json({ ok: true });
      }
      if (path[2] === "harness") {
        const tail = "/" + path.slice(3).join("/");
        if (
          !scientificRoutes.some(
            (r) =>
              r.method === method &&
              new RegExp(
                "^" + r.path.replace(/\{[^}]+\}/g, "[^/]+") + "$",
              ).test(tail),
          )
        )
          throw new ApiError(404, "Unknown operation");
        if (entity.data.archived && method !== "GET")
          throw new ApiError(409, "Conversation is archived");
        let payload: Record<string, unknown> | undefined;
        const upload = tail === "/workspace/upload";
        if (!upload && !["GET", "HEAD"].includes(method))
          payload = await body(request);
        const role: Role = tail.startsWith("/data/agent")
          ? "data"
          : tail.startsWith("/evaluator/agent")
            ? "evaluator"
            : "search";
        const execute = [
          "/start",
          "/data/agent",
          "/evaluator/agent/start",
          "/test",
          "/data/agent/test",
          "/evaluator/agent/test",
          "/control/command",
        ].includes(tail);
        if (execute) {
          const actualRole =
            tail === "/control/command" && roles.includes(payload?.role as Role)
              ? (payload!.role as Role)
              : role;
          if (
            tail !== "/control/command" ||
            ["resume", "message", "next_c", "next_r"].includes(
              String(payload?.action),
            )
          )
            await supplyModel(user, entity, actualRole);
        }
        const key = request.headers.get("idempotency-key");
        if (
          [
            "/start",
            "/data/agent",
            "/evaluator/agent/start",
            "/control/command",
          ].includes(tail) &&
          !key
        )
          throw new ApiError(422, "Idempotency key required");
        const headers: Record<string, string> = {
          ...(key ? { "idempotency-key": key } : {}),
          ...(!upload ? { "content-type": "application/json" } : {}),
        };
        const init: RequestInit & { duplex?: string } = { method, headers };
        if (upload) {
          init.body = request.body;
          init.duplex = "half";
        } else if (payload) init.body = JSON.stringify(payload);
        const response = await harness(
          `/v1/sessions/${sid}${tail === "/" ? "" : tail}${request.nextUrl.search}`,
          init,
        );
        return new Response(response.body, {
          status: response.status,
          headers: {
            "content-type":
              response.headers.get("content-type") || "application/json",
            ...(response.headers.has("content-disposition")
              ? {
                  "content-disposition": response.headers.get(
                    "content-disposition",
                  )!,
                }
              : {}),
            "cache-control": "no-store",
          },
        });
      }
    }
    throw new ApiError(404, "Not found");
  } catch (error) {
    if (error instanceof z.ZodError)
      return json({ error: { code: "invalid_fields", message: "Invalid request fields" } }, 422);
    if (error instanceof ApiError)
      return json({ error: { code: error.code, message: error.message } }, error.status);
    return json(
      { error: { code: "internal_error", message: "Operation failed; refresh and retry" } },
      500,
    );
  }
}
export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
};
