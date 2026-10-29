import { z } from "zod";
import { repository, type Entity } from "./db";
import { ApiError, decrypt, encrypt, type Identity } from "./security";

export const roles = ["search", "data", "evaluator"] as const;
export type Role = (typeof roles)[number];
const input = z.object({
  name: z.string().min(1).max(100),
  provider: z.enum([
    "openrouter",
    "openai",
    "azure",
    "compatible",
    "deepseek",
    "siliconflow",
    "gemini",
    "lmstudio",
  ]),
  model: z.string().min(1).max(256),
  endpoint: z.string().max(2048).default(""),
  api_version: z.string().max(100).optional(),
  api_key: z.string().max(16384).optional(),
  shared: z.boolean().default(false),
  isDefault: z.boolean().default(false),
});
export type Model = Omit<z.infer<typeof input>, "api_key"> & { secret: string };
export function summarize(entity: Entity<Model>) {
  const { secret, ...data } = entity.data;
  return {
    ...data,
    id: entity.id,
    owner: entity.owner,
    configured: Boolean(secret),
  };
}
export async function visibleModels(user: Identity) {
  return (await repository.list<Model>("model"))
    .filter((m) => m.owner === user.id || m.data.shared)
    .map(summarize);
}
export async function saveModel(user: Identity, value: unknown, id?: string) {
  const parsed = input.parse(value);
  if (parsed.endpoint && !/^https?:\/\//.test(parsed.endpoint))
    throw new ApiError(422, "Endpoint must use HTTP or HTTPS");
  if (parsed.shared && user.role !== "admin")
    throw new ApiError(
      403,
      "Only administrators can publish shared configurations",
    );
  const previous = id ? await repository.get<Model>(id) : undefined;
  if (
    id &&
    (!previous ||
      previous.kind !== "model" ||
      (previous.owner !== user.id &&
        !(user.role === "admin" && previous.data.shared)))
  )
    throw new ApiError(404, "Model configuration not found");
  const { api_key, ...details } = parsed;
  const secret = api_key ? encrypt(api_key) : previous?.data.secret;
  if (!secret) throw new ApiError(422, "An API key is required");
  if (parsed.provider === "azure" && (!parsed.endpoint || !parsed.api_version))
    throw new ApiError(422, "Azure requires endpoint and API version");
  return repository.transaction(async (repo) => {
    if (parsed.isDefault)
      for (const model of await repo.list<Model>("model"))
        if (
          model.data.isDefault &&
          model.data.shared === parsed.shared &&
          (parsed.shared || model.owner === user.id)
        )
          await repo.update(model, { ...model.data, isDefault: false });
    const data = { ...details, secret };
    if (previous) {
      await repo.update(previous, data);
      return summarize({ ...previous, data });
    }
    return summarize(await repo.insert("model", user.id, data));
  });
}
export async function resolveModel(user: Identity, id?: string) {
  const visible = (await repository.list<Model>("model")).filter(
    (m) => m.owner === user.id || m.data.shared,
  );
  const model = id
    ? visible.find((m) => m.id === id)
    : visible.find((m) => m.owner === user.id && m.data.isDefault) ||
      visible.find((m) => m.data.shared && m.data.isDefault);
  if (!model) throw new ApiError(409, "Select or configure a model first");
  const {
    secret,
    name: _name,
    shared: _shared,
    isDefault: _default,
    ...configuration
  } = model.data;
  return { ...configuration, api_key: decrypt(secret) };
}
