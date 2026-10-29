import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
} from "node:crypto";
import { cookies } from "next/headers";
import { hash, verify } from "@node-rs/argon2";
import { repository, type Repository } from "./db";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
  get code(): string {
    return ({401: 'unauthorized', 403: 'forbidden', 404: 'not_found', 409: 'conflict',
             413: 'request_too_large', 422: 'invalid_fields', 429: 'too_many_requests',
             503: 'service_unavailable', 504: 'timeout'} as Record<number, string>)[this.status] || 'internal_error';
  }
}
export type User = {
  username: string;
  passwordHash: string;
  role: "admin" | "user";
  disabled: boolean;
  createdAt: number;
};
export type Identity = { id: string; username: string; role: "admin" | "user" };
type Login = { userId: string; expiresAt: number; userVersion: number };
type Invite = { expiresAt: number; used: boolean };
export type RegistrationMode = "open" | "invite" | "admin";
export const digest = (value: string) =>
  createHash("sha256").update(value).digest("hex");
export const randomToken = () => randomBytes(32).toString("base64url");
const master = () => {
  const key = Buffer.from(process.env.CREDENTIAL_MASTER_KEY || "", "base64");
  if (key.length !== 32)
    throw new ApiError(503, "Credential encryption key is not configured");
  return key;
};
export function encrypt(secret: string): string {
  const nonce = randomBytes(12),
    cipher = createCipheriv("aes-256-gcm", master(), nonce);
  return Buffer.concat([
    nonce,
    cipher.update(secret, "utf8"),
    cipher.final(),
    cipher.getAuthTag(),
  ]).toString("base64");
}
export function decrypt(value: string): string {
  const bytes = Buffer.from(value, "base64"),
    cipher = createDecipheriv("aes-256-gcm", master(), bytes.subarray(0, 12));
  cipher.setAuthTag(bytes.subarray(-16));
  return Buffer.concat([
    cipher.update(bytes.subarray(12, -16)),
    cipher.final(),
  ]).toString("utf8");
}

export async function createUser(
  username: string,
  password: string,
  role: "admin" | "user" = "user",
  repo: Repository = repository,
) {
  username = username.trim().toLowerCase();
  if (
    !/^[a-z0-9_.-]{3,64}$/.test(username) ||
    password.length < 12 ||
    password.length > 1024
  )
    throw new ApiError(
      422,
      "Username must be 3–64 characters; password must be 12–1024 characters",
    );
  if (await repo.byKey(`username:${username}`))
    throw new ApiError(409, "Username is unavailable");
  const passwordHash = await hash(password, {
    memoryCost: 19456,
    timeCost: 2,
    parallelism: 1,
  });
  return repo.insert<User>(
    "user",
    "",
    { username, passwordHash, role, disabled: false, createdAt: Date.now() },
    `username:${username}`,
  );
}

export async function registrationMode(): Promise<RegistrationMode> {
  return (
    (await repository.byKey<{ mode: RegistrationMode }>("setting:registration"))
      ?.data.mode || "open"
  );
}
export async function register(
  username: string,
  password: string,
  invitation?: string,
) {
  const mode = await registrationMode();
  if (mode === "admin") throw new ApiError(403, "Registration is closed");
  return repository.transaction(async (repo) => {
    if (mode === "invite") {
      const invite = await repo.byKey<Invite>(
        `invite:${digest(invitation || "")}`,
      );
      if (!invite || invite.data.used || invite.data.expiresAt <= Date.now())
        throw new ApiError(403, "Invitation is invalid or expired");
      await repo.update(invite, { ...invite.data, used: true });
    }
    return createUser(username, password, "user", repo);
  });
}

export async function login(username: string, password: string) {
  const user = await repository.byKey<User>(
    `username:${username.trim().toLowerCase()}`,
  );
  if (
    !user ||
    user.data.disabled ||
    !(await verify(user.data.passwordHash, password))
  )
    throw new ApiError(401, "Invalid username or password");
  const token = randomToken(),
    expiresAt = Date.now() + 7 * 86400000;
  await repository.insert<Login>(
    "login",
    user.id,
    { userId: user.id, expiresAt, userVersion: user.version },
    `login:${digest(token)}`,
  );
  (await cookies()).set("astral_session", token, {
    httpOnly: true,
    sameSite: "lax",
    secure:
      process.env.COOKIE_SECURE === "true" ||
      process.env.APP_ORIGIN?.startsWith("https://") === true,
    path: "/",
    maxAge: 7 * 86400,
  });
  return { id: user.id, username: user.data.username, role: user.data.role };
}

export async function requireUser(admin = false): Promise<Identity> {
  const token = (await cookies()).get("astral_session")?.value;
  const session = token
    ? await repository.byKey<Login>(`login:${digest(token)}`)
    : undefined;
  if (!session || session.data.expiresAt <= Date.now())
    throw new ApiError(401, "Please sign in");
  const user = await repository.get<User>(session.owner);
  if (
    !user ||
    user.kind !== "user" ||
    user.data.disabled ||
    session.data.userVersion !== user.version
  )
    throw new ApiError(401, "Account unavailable");
  if (admin && user.data.role !== "admin")
    throw new ApiError(403, "Administrator access required");
  return { id: user.id, username: user.data.username, role: user.data.role };
}
export async function revoke(userId: string) {
  for (const session of await repository.list("login", userId))
    await repository.remove(session.id);
}
export async function logout() {
  const jar = await cookies(),
    token = jar.get("astral_session")?.value;
  if (token) {
    const session = await repository.byKey(`login:${digest(token)}`);
    if (session) await repository.remove(session.id);
  }
  jar.delete("astral_session");
}
export async function invitation(owner: string) {
  const token = randomToken();
  await repository.insert<Invite>(
    "invite",
    owner,
    { expiresAt: Date.now() + 7 * 86400000, used: false },
    `invite:${digest(token)}`,
  );
  return token;
}
export function checkOrigin(request: Request) {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return;
  const origin = request.headers.get("origin"),
    expected = process.env.APP_ORIGIN;
  if (!expected || origin !== new URL(expected).origin)
    throw new ApiError(403, "Untrusted request origin");
}
const limits = new Map<string, { count: number; until: number }>();
export function rateLimit(key: string, max = 10, window = 60000) {
  const now = Date.now();
  for (const [k, v] of limits) if (v.until <= now) limits.delete(k);
  const entry = limits.get(key) || { count: 0, until: now + window };
  if (++entry.count > max)
    throw new ApiError(429, "Too many attempts; retry later");
  limits.set(key, entry);
}
