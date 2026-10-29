const pending = new Map<string, string>();
let active = 0;
const queue: (() => void)[] = [];
async function withSlot<T>(work: () => Promise<T>): Promise<T> {
  await new Promise<void>((resolve) => {
    if (active < 3) {
      active++;
      resolve();
    } else queue.push(resolve);
  });
  try {
    return await work();
  } finally {
    active--;
    const next = queue.shift();
    if (next) {
      active++;
      next();
    }
  }
}
export async function api<T = any>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const signature = `${method}:${path}:${JSON.stringify(data)}`;
  const key = pending.get(signature) || crypto.randomUUID();
  const tracked =
    path === "conversations" ||
    /\/harness\/(start|data\/agent|evaluator\/agent\/start|control\/command)$/.test(
      path,
    );
  if (method !== "GET" && tracked) pending.set(signature, key);
  let response!: Response, result: any;
  for (let attempt = 0; attempt < 3; attempt++) {
    ({ response, result } = await withSlot(async () => {
      const response = await fetch(`/api/${path}`, {
        method,
        signal: AbortSignal.timeout(40000),
        headers: { "content-type": "application/json", "idempotency-key": key },
        ...(data === undefined ? {} : { body: JSON.stringify(data) }),
      });
      return { response, result: await response.json() };
    }));
    if (
      method !== "GET" ||
      ![429, 503].includes(response.status) ||
      attempt === 2
    )
      break;
    await new Promise((resolve) =>
      setTimeout(resolve, 1000 + Math.random() * 1000),
    );
  }
  if (!response.ok) {
    if (response.status < 500) pending.delete(signature);
    throw new Error(
      result.error?.message || `Request failed (${response.status})`,
    );
  }
  pending.delete(signature);
  return result;
}
export type Role = "search" | "data" | "evaluator";
export type ModelSummary = {
  id: string;
  owner: string;
  name: string;
  provider: string;
  endpoint: string;
  model: string;
  api_version?: string;
  shared: boolean;
  isDefault: boolean;
};
export type Conversation = {
  id: string;
  name: string;
  models: Partial<Record<Role, string>>;
};
