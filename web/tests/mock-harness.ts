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
        run_id: "",
        data_state: "idle",
        data_interaction_state: "idle",
        evaluator_interaction_state: "idle",
        data_context: { revision: 0 },
        files: [],
        events: [],
        agentEvents: { data: [], evaluator: [], search: [] },
        context_ready: false,
        settings: {
          llm_provider: "compatible",
          llm_model: "test-model",
          tool_parser: "openai",
          llm_max_tokens: null,
          max_restart_loop: 2,
          global_width: 2,
          max_refinement_depth: 2,
          local_sample_size: 1,
          restart_top_k: 2,
          max_workers: 0,
          tools: [],
          skills: [],
          validation_fraction: 0.2,
          ranking_metric: "mse",
        },
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
  if (path === "/capabilities")
    return reply({
      tools: [],
      skills: [],
      default_tools: [],
      default_skills: [],
    });
  if (path === "/data/prompts")
    return reply({
      problem_description: "Find the relation between x and y",
      system_prompt: "You are a scientist",
      user_prompt: "Find an interpretable formula",
    });
  if (path.endsWith("/settings") && req.method !== "GET") {
    if (path === "/settings") Object.assign(state.settings, body);
    else if (path.startsWith("/data"))
      Object.assign(state.data_agent_settings, body);
    else Object.assign(state.evaluator_agent_settings, body);
    return reply(state);
  }
  if (path === "/workspace/preview") return reply({ text: "x,y\n1,2\n2,4" });
  if (path === "/data/discovery-tasks") return reply({ tasks: [] });
  if (path === "/data/context" && !state.context_ready)
    return reply({
      has_manifest: false,
      columns: [],
      data: [],
      rows: 0,
      revision: 0,
    });
  if (path === "/data/context")
    return reply({
      revision: state.context_ready ? 1 : 0,
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
    state.data_context = { revision: 1 };
    const events =
      state.agentEvents[path.startsWith("/data") ? "data" : "evaluator"];
    events.push({
      seq: events.length + 1,
      kind: "assistant_completed",
      timestamp: Date.now() / 1000,
      payload: {
        response_id: randomUUID(),
        turn: 1,
        content: "Task completed",
        type: "complete",
      },
    });
    return reply(
      { ...state, operation_id: req.headers["idempotency-key"] },
      202,
    );
  }
  if (path === "/start") {
    state.state = "running";
    state.run_id = "mock-run";
    state.interaction_state = "running";
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
  if (
    [
      "/control/events",
      "/data/agent/events",
      "/evaluator/agent/events",
    ].includes(path)
  ) {
    const role = path.startsWith("/data")
      ? "data"
      : path.startsWith("/evaluator")
        ? "evaluator"
        : "search";
    return reply({
      events: state.agentEvents[role].filter(
        (e: any) => e.seq > Number(url.searchParams.get("after_seq") || 0),
      ),
      has_more: false,
    });
  }
  if (path === "/candidates") return reply({ records: state.topk_records });
  if (path === "/records")
    return reply({
      records:
        state.state === "running"
          ? [
              {
                node_id: "R1-C1-L1-K1",
                seq: 1,
                coord: { R: 1, C: 1, L: 1, K: 1 },
                parents: [],
                run_id: "mock-run",
                core: {
                  formula: "2*x",
                  tool_names: [],
                  metrics: { mse: 0, r2: 1 },
                },
                detail: { prompt: [] },
              },
            ]
          : [],
    });
  if (path === "/evaluator")
    return reply({
      selected: "default",
      source: "# evaluator",
      editable: true,
      evaluators: [],
      settings: {
        validation_fraction: 0.2,
        split_random_state: 42,
        split_by: "random",
        ranking_metric: "mse",
        larger_is_better: false,
      },
    });
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
