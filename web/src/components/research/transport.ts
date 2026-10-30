import { api } from "@/lib/client";

export const selectionKey = "sr-harness-conversation";
const sessionPaths: Record<string, string> = {
  "/session": "",
  "/session/start": "/start",
  "/session/settings": "/settings",
  "/session/capabilities": "/capabilities",
  "/session/test": "/test",
};

/** Presentation compatibility only. Every scientific request still goes through the owned Next API. */
export function researchTransport(signal: AbortSignal, conversation?: string) {
  const selected = () =>
    conversation || sessionStorage.getItem(selectionKey) || "";
  async function conversations() {
    const result = await api("conversations");
    if (!result.conversations.length) {
      await api("conversations", "POST", {});
      return conversations();
    }
    const id = result.conversations.some((c: any) => c.id === selected())
      ? selected()
      : result.conversations[0].id;
    sessionStorage.setItem(selectionKey, id);
    return {
      selected: id,
      read_only: false,
      conversations: result.conversations.map((c: any) => ({
        ...c,
        updated_at: new Date(c.createdAt || Date.now()).toISOString(),
      })),
    };
  }
  async function json(url: string, data?: any, method = "POST"): Promise<any> {
    if (signal.aborted) throw new DOMException("Unmounted", "AbortError");
    const parsed = new URL(url, location.origin),
      path = parsed.pathname.replace(/^\/api/, "");
    const verb = data === undefined ? "GET" : method;
    if (path === "/version") return api("version");
    if (path === "/conversations") {
      if (verb === "GET") return conversations();
      return api("conversations", verb, data);
    }
    const match = path.match(
      /^\/conversations\/([^/]+)(?:\/(select|export))?$/,
    );
    if (match) {
      const id = match[1];
      if (match[2] === "select") {
        const list = await api("conversations");
        if (!list.conversations.some((c: any) => c.id === id))
          throw Error("Conversation not found");
        sessionStorage.setItem(selectionKey, id);
        return { selected: id };
      }
      await api(`conversations/${id}`, verb, data);
      return verb === "DELETE" ? conversations() : { id, ...data };
    }
    if (!selected()) await conversations();
    if (path === "/runs") {
      const status = await api(`conversations/${selected()}/harness`);
      return {
        runs: status.run_id
          ? [{ run_id: status.run_id, state: status.state }]
          : [],
      };
    }
    const run = path.match(/^\/runs\/[^/]+\/records(\/[^/]+)?$/);
    const tail = run
      ? "/records" + (run[1] || "")
      : (sessionPaths[path] ?? path);
    const payload = data && { ...data };
    // Model/endpoint/key are selected as one database profile, never pieced together in the browser.
    if (payload)
      for (const key of ["llm_provider", "llm_model", "proxy"])
        delete payload[key];
    const result = await api(
      `conversations/${selected()}/harness${tail}${parsed.search}`,
      verb,
      payload,
    );
    // Asynchronous commands return receipts; the existing interaction logic consumes a snapshot.
    if (
      verb !== "GET" &&
      [
        "/start",
        "/data/agent",
        "/evaluator/agent/start",
        "/control/command",
      ].includes(tail)
    )
      return api(`conversations/${selected()}/harness`);
    return result;
  }
  function fileURL(url: string, id = selected()) {
    const parsed = new URL(url, location.origin);
    const conversationExport = parsed.pathname.match(
      /^\/api\/conversations\/([^/]+)\/export$/,
    );
    if (conversationExport)
      return `/api/conversations/${conversationExport[1]}/harness/export`;
    return `/api/conversations/${id}/harness${parsed.pathname.replace(/^\/api/, "")}${parsed.search}`;
  }
  async function fetchFile(url: string, init: RequestInit = {}) {
    return fetch(fileURL(url), {
      ...init,
      signal: AbortSignal.any([signal, ...(init.signal ? [init.signal] : [])]),
    });
  }
  return { json, fileURL, fetchFile, selected };
}
