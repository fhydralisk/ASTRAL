import { ApiError } from "./security";
import type { paths, components } from "@/lib/harness-schema";
export type HarnessPath = keyof paths;
export async function harness(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const base = process.env.HARNESS_URL || "http://127.0.0.1:8000";
  const token = process.env.HARNESS_SERVICE_TOKEN;
  if (!token) throw new ApiError(503, "Harness connection is not configured");
  const headers = new Headers(init.headers);
  headers.set("authorization", `Bearer ${token}`);
  try {
    const response = await fetch(new URL(path, base), {
      ...init,
      headers,
      cache: "no-store",
      signal: AbortSignal.timeout(35000),
    });
    if (!response.ok) {
      // Internal errors may contain provider responses; never reflect arbitrary bodies.
      const status = response.status;
      if (status === 409) {
        const error = await response.json().catch(() => null);
        if (error?.error?.code === "context_data_missing")
          throw new ApiError(
            409,
            "context.data/manifest.json does not exist; prepare data first",
          );
      } else await response.body?.cancel();
      throw new ApiError(
        status,
        status === 429
          ? "Harness capacity exceeded; retry shortly"
          : status === 504
            ? "Operation timed out; check state before retrying"
            : `Harness operation failed (${status})`,
      );
    }
    return response;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      503,
      "Harness is unavailable; check session state before retrying",
    );
  }
}
export async function harnessJSON<T = Record<string, unknown>>(
  path: string,
  method = "GET",
  body?: unknown,
  idempotencyKey?: string,
): Promise<T> {
  const response = await harness(path, {
    method,
    headers: {
      "content-type": "application/json",
      ...(idempotencyKey ? { "idempotency-key": idempotencyKey } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  return response.status === 204 ? ({} as T) : response.json();
}

export function createRemoteSession(
  body: components["schemas"]["CreateSession"],
) {
  return harnessJSON<components["schemas"]["SessionInfo"]>(
    "/v1/sessions",
    "POST",
    body,
  );
}
export function setRemoteModel(
  sessionId: string,
  role: "search" | "data" | "evaluator",
  body: components["schemas"]["ModelConfiguration"],
) {
  return harnessJSON(
    `/v1/sessions/${sessionId}/credentials/${role}`,
    "PUT",
    body,
  );
}
