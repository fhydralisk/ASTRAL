import { repository, type Entity } from "./db";
import { createRemoteSession, setRemoteModel } from "./harness";
import { ApiError, type Identity } from "./security";
import { resolveModel, type Role } from "./models";

export type Conversation = {
  name: string;
  creationKey: string;
  harnessId?: string;
  archived: boolean;
  createdAt: number;
  models: Partial<Record<Role, string>>;
};
export async function owned(
  user: Identity,
  id: string,
): Promise<Entity<Conversation>> {
  const entity = await repository.get<Conversation>(id);
  if (!entity || entity.kind !== "conversation" || entity.owner !== user.id)
    throw new ApiError(404, "Conversation not found");
  return entity;
}
export async function ensureHarness(entity: Entity<Conversation>) {
  if (entity.data.harnessId) return entity.data.harnessId;
  const result = await createRemoteSession({
    tags: { user_ref: entity.owner, conversation_ref: entity.id },
    idempotency_key: entity.id,
  });
  try {
    await repository.update(entity, { ...entity.data, harnessId: result.id });
  } catch {
    const latest = await repository.get<Conversation>(entity.id);
    if (latest?.data.harnessId !== result.id)
      throw new ApiError(409, "Session creation is being reconciled; retry");
  }
  return result.id;
}
export async function createConversation(
  user: Identity,
  key: string,
  name: string,
) {
  if (!key || key.length > 100)
    throw new ApiError(422, "A valid idempotency key is required");
  const unique = `conversation:${user.id}:${key}`;
  let entity = await repository.byKey<Conversation>(unique);
  if (!entity) {
    try {
      entity = await repository.insert<Conversation>(
        "conversation",
        user.id,
        {
          name: name || "Unnamed Conversation",
          creationKey: key,
          archived: false,
          createdAt: Date.now(),
          models: {},
        },
        unique,
      );
    } catch {
      entity = await repository.byKey<Conversation>(unique);
      if (!entity) throw new ApiError(409, "Unable to create conversation");
    }
  }
  await ensureHarness(entity);
  return (await repository.get<Conversation>(entity.id))!;
}
export async function supplyModel(
  user: Identity,
  conversation: Entity<Conversation>,
  role: Role,
) {
  const configuration = await resolveModel(
    user,
    conversation.data.models[role],
  );
  await setRemoteModel(await ensureHarness(conversation), role, configuration);
}
