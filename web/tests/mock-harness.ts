// Test-only remote Harness double. No test mode or bypass is built into production code.
import { createServer } from "node:http";
import { randomUUID } from "node:crypto";
const sessions = new Map<string, any>(),
  creations = new Map<string, string>();
createServer(async (req, res) => {
  if (
    req.headers.authorization !== "Bearer playwright-internal-token-12345678"
  ) {
    res.writeHead(401).end();
    return;
  }
  const url = new URL(req.url!, "http://localhost"),
    chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks),
    isUpload = url.pathname.endsWith("/workspace/upload");
  const body = isUpload ? {} : raw.length ? JSON.parse(raw.toString()) : {};
  const reply = (value: unknown, status = 200) => {
    res
      .writeHead(status, { "content-type": "application/json" })
      .end(JSON.stringify(value));
  };
  if (url.pathname === "/v1/sessions" && req.method === "POST") {
    let id = creations.get(body.idempotency_key);
    if (!id) {
      id = randomUUID().replaceAll("-", "");
      creations.set(body.idempotency_key, id);
      sessions.set(id, {
        state: "idle",
        files: [],
        events: [],
        context_ready: false,
        settings: {},
        data_agent_settings: {},
        evaluator_agent_settings: {},
        topk_records: [],
      });
    }
    return reply({ id }, 201);
  }
  const sid = url.pathname.split("/")[3],
    state = sessions.get(sid),
    path = "/" + url.pathname.split("/").slice(4).join("/");
  if (!state) return reply({ error: { message: "Not found" } }, 404);
  if (path.startsWith("/credentials/")) {
    res.writeHead(204).end();
    return;
  }
  if (path === "/workspace/upload") {
    state.files.push({
      path: url.searchParams.get("path"),
      name: url.searchParams.get("path"),
      directory: false,
    });
    return reply({ ok: true });
  }
  if (path === "/workspace") return reply({ entries: state.files });
  if (path === "/workspace/preview") return reply({ text: "x,y\n1,2\n2,4" });
  if (path === "/data/discovery-tasks") return reply({ tasks: [] });
  if (path === "/data/context")
    return reply({
      rows: 2,
      columns: ["x", "y"],
      preview_columns: ["x", "y"],
      features: ["x"],
      target: "y",
      data: [
        { x: 1, y: 2 },
        { x: 2, y: 4 },
      ],
    });
  if (path === "/data/agent" || path === "/evaluator/agent/start") {
    state.context_ready = true;
    state.events.push({
      seq: state.events.length + 1,
      type: "assistant_message",
      payload: { content: "Task completed" },
    });
    return reply(
      { ...state, operation_id: req.headers["idempotency-key"] },
      202,
    );
  }
  if (path === "/start") {
    state.state = "running";
    state.topk_records = [{ formula: "2*x", mse: 0 }];
    return reply(
      { ...state, operation_id: req.headers["idempotency-key"] },
      202,
    );
  }
  if (path === "/control/command") {
    state.interaction_state =
      body.action === "pause"
        ? "paused"
        : body.action === "stop"
          ? "idle"
          : "running";
    return reply({ operation_id: req.headers["idempotency-key"] }, 202);
  }
  if (path === "/control/events")
    return reply({
      events: state.events.filter(
        (e: any) => e.seq > Number(url.searchParams.get("after_seq") || 0),
      ),
    });
  if (path === "/candidates") return reply({ records: state.topk_records });
  if (path === "/records")
    return reply({
      records:
        state.state === "running"
          ? [{ node_id: "R1-C1-L1-K1", core: { formula: "2*x" } }]
          : [],
    });
  if (path === "/evaluator")
    return reply({ selected: "default", source: "# evaluator" });
  if (path === "/export") {
    res
      .writeHead(200, {
        "content-type": "application/zip",
        "content-disposition": 'attachment; filename="conversation.zip"',
      })
      .end("test-export");
    return;
  }
  return reply(state);
}).listen(8123, "127.0.0.1");
