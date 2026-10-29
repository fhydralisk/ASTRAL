"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { DataVisualization } from "./data-visualization";
import {
  api,
  type Conversation,
  type ModelSummary,
  type Role,
} from "@/lib/client";
import { JsonEditor, Timeline } from "./common";
import { AgentSettings } from "./agent-settings";
import { Candidates } from "./candidates";
import { SearchTree } from "./search-tree";

type Call = (path: string, method?: string, payload?: unknown) => Promise<any>;
export function Workbench({
  conversation,
  models,
  refreshConversations,
  en,
  notify,
}: {
  conversation: Conversation;
  models: ModelSummary[];
  refreshConversations: () => Promise<void>;
  en: boolean;
  notify: (message: string) => void;
}) {
  const [tab, setTab] = useState<Role>("data"),
    [snapshot, setSnapshot] = useState<any>({}),
    [events, setEvents] = useState<Record<Role, any[]>>({
      data: [],
      evaluator: [],
      search: [],
    }),
    [records, setRecords] = useState<any[]>([]),
    [busy, setBusy] = useState(false);
  const cursors = useRef<Record<Role, number>>({
    data: 0,
    evaluator: 0,
    search: 0,
  });
  const call: Call = useCallback(
    (path, method = "GET", payload) =>
      api(`conversations/${conversation.id}/harness${path}`, method, payload),
    [conversation.id],
  );
  const action = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await fn();
      } catch (e) {
        notify(String(e));
      } finally {
        setBusy(false);
      }
    },
    [notify],
  );
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const [status, ...batches] = await Promise.all([
          call(""),
          ...(["data", "evaluator", "search"] as Role[]).map((role) =>
            call(
              `/control/events?role=${role}&after_seq=${cursors.current[role]}`,
            ),
          ),
        ]);
        if (!active) return;
        setSnapshot(status);
        (["data", "evaluator", "search"] as Role[]).forEach((role, i) => {
          const batch = batches[i];
          const rows = batch.events || [];
          if (rows.length) {
            cursors.current[role] = Number(
              batch.last_seq ??
                batch.latest_seq ??
                rows.at(-1)?.seq ??
                rows.at(-1)?.sequence ??
                cursors.current[role],
            );
            setEvents((prev) => ({
              ...prev,
              [role]: [...prev[role], ...rows].slice(-2000),
            }));
          }
        });
        const currentRecords: any[] = [];
        let after = 0;
        while (active) {
          const result = await call("/records?after_seq=" + after);
          const page = result.records || [];
          currentRecords.push(...page);
          if (page.length < 32) break;
          const next = Number(page.at(-1)?.seq);
          if (!Number.isFinite(next) || next <= after) break;
          after = next;
        }
        if (active) setRecords(currentRecords);
      } catch (e) {
        if (active) notify(String(e));
      } finally {
        if (active) timer = setTimeout(poll, 1500);
      }
    }
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [call, notify]);
  async function command(actionName: string) {
    return call("/control/command", "POST", { role: tab, action: actionName });
  }
  return (
    <div className="research-grid">
      <aside className="workspace-panel">
        <Files
          call={call}
          action={action}
          conversationId={conversation.id}
          en={en}
        />
      </aside>
      <main className="research-main">
        <div className="stage-tabs">
          {(["data", "evaluator", "search"] as Role[]).map((role, i) => (
            <button
              key={role}
              className={tab === role ? "active" : ""}
              onClick={() => setTab(role)}
            >
              {i + 1}.{" "}
              {role === "data"
                ? en
                  ? "Data preparation"
                  : "数据准备"
                : role === "evaluator"
                  ? en
                    ? "Task & Evaluator"
                    : "任务与评测器"
                  : en
                    ? "Symbolic regression"
                    : "符号回归"}
            </button>
          ))}
        </div>
        <div className="toolbar">
          <span className="status">
            {snapshot.state || "…"} ·{" "}
            {tab === "data"
              ? snapshot.data_state
              : tab === "evaluator"
                ? snapshot.evaluator_agent_state
                : snapshot.interaction_state}
          </span>
          <select
            aria-label="Model configuration"
            value={conversation.models?.[tab] || ""}
            onChange={(e) =>
              action(async () => {
                await api(`conversations/${conversation.id}`, "PATCH", {
                  models: { ...conversation.models, [tab]: e.target.value },
                });
                await refreshConversations();
              })
            }
          >
            <option value="">Default / 默认模型</option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
                {m.shared ? " · Shared" : ""}
              </option>
            ))}
          </select>
          <button
            disabled={busy}
            onClick={() =>
              action(async () => {
                const result = await call(
                  tab === "data"
                    ? "/data/agent/test"
                    : tab === "evaluator"
                      ? "/evaluator/agent/test"
                      : "/test",
                  "POST",
                  {},
                );
                notify(
                  result.ok
                    ? "Connection and tool test passed / 连接与工具测试通过"
                    : "Model test failed / 模型测试失败",
                );
              })
            }
          >
            Test / 测试
          </button>
          {["pause", "resume", "force_pause", "stop"].map((c) => (
            <button
              key={c}
              disabled={busy}
              onClick={() => action(() => command(c))}
            >
              {c === "pause"
                ? "Ⅱ"
                : c === "resume"
                  ? "▶"
                  : c === "stop"
                    ? "■"
                    : "⏸"}{" "}
              {c}
            </button>
          ))}
        </div>
        <div className="stage-content">
          {tab === "data" && <DataPanel call={call} action={action} en={en} />}{" "}
          {tab === "evaluator" && (
            <EvaluatorPanel call={call} action={action} />
          )}{" "}
          {tab === "search" && (
            <SearchPanel
              call={call}
              action={action}
              snapshot={snapshot}
              records={records}
              en={en}
            />
          )}
          <AgentComposer
            role={tab}
            call={call}
            action={action}
            disabled={busy}
            en={en}
          />
          <Timeline events={events[tab]} />
          <AgentSettings
            role={tab}
            call={call}
            value={
              tab === "search"
                ? snapshot.settings
                : tab === "data"
                  ? snapshot.data_agent_settings
                  : snapshot.evaluator_agent_settings
            }
          />
        </div>
      </main>
      <aside className="candidate-panel">
        <Candidates snapshot={snapshot} call={call} en={en} />
      </aside>
    </div>
  );
}

function AgentComposer({
  role,
  call,
  action,
  disabled,
  en,
}: {
  role: Role;
  call: Call;
  action: (fn: () => Promise<unknown>) => Promise<void>;
  disabled: boolean;
  en: boolean;
}) {
  const [message, setMessage] = useState("");
  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        action(async () => {
          await call(
            role === "data"
              ? "/data/agent"
              : role === "evaluator"
                ? "/evaluator/agent/start"
                : "/control/command",
            "POST",
            role === "search"
              ? { role, action: "message", message }
              : { message },
          );
          setMessage("");
        });
      }}
    >
      <textarea
        aria-label="Agent instruction"
        placeholder={en ? "Describe your instruction…" : "输入指令或人工指导…"}
        required
        value={message}
        onChange={(e) => setMessage(e.target.value)}
      />
      <button className="primary" disabled={disabled}>
        {en ? "Send" : "发送"}
      </button>
    </form>
  );
}

function Files({
  call,
  action,
  conversationId,
  en,
}: {
  call: Call;
  action: (fn: () => Promise<unknown>) => Promise<void>;
  conversationId: string;
  en: boolean;
}) {
  const [entries, setEntries] = useState<any[]>([]),
    [preview, setPreview] = useState<any>(null);
  async function refresh() {
    setEntries((await call("/workspace?recursive=true")).entries || []);
  }
  useEffect(() => {
    let active = true;
    const timer = setInterval(() => {
      if (active) refresh().catch(() => {});
    }, 5000);
    refresh().catch(() => {});
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [call]);
  function rows(items: any[]): React.ReactNode {
    return items.map((f) => (
      <div className="file" key={f.path}>
        <button
          title={f.path}
          onClick={() =>
            action(async () => {
              if (!f.directory)
                setPreview(
                  await call(
                    "/workspace/preview?path=" + encodeURIComponent(f.path),
                  ),
                );
            })
          }
        >
          {f.directory ? "▸" : "·"} {f.name} {f.locked || f.mounted ? "🔒" : ""}
        </button>
        <details>
          <summary>⋯</summary>
          <a
            href={`/api/conversations/${conversationId}/harness/workspace/download?path=${encodeURIComponent(f.path)}`}
          >
            Download / 下载
          </a>
          <button
            onClick={() =>
              action(async () => {
                await call("/workspace/lock", "PUT", {
                  path: f.path,
                  locked: !f.locked,
                });
                await refresh();
              })
            }
          >
            Lock / 锁定
          </button>
          <button
            onClick={() => {
              const destination = prompt("Destination path", f.path);
              if (destination)
                action(async () => {
                  await call("/workspace", "PATCH", {
                    source: f.path,
                    destination,
                  });
                  await refresh();
                });
            }}
          >
            Rename / 移动
          </button>
          <button
            onClick={() => {
              if (confirm("Delete / 删除 " + f.path + "?"))
                action(async () => {
                  await call(
                    "/workspace?path=" + encodeURIComponent(f.path),
                    "DELETE",
                  );
                  await refresh();
                });
            }}
          >
            Delete / 删除
          </button>
        </details>
        {f.children && <div className="file-children">{rows(f.children)}</div>}
      </div>
    ));
  }
  return (
    <>
      <h3>{en ? "Workspace" : "工作区"}</h3>
      <label className="upload">
        ＋ {en ? "Upload files" : "上传文件"}
        <input
          type="file"
          multiple
          onChange={(e) => {
            const files = Array.from(e.target.files || []);
            action(async () => {
              for (const file of files) {
                const response = await fetch(
                  `/api/conversations/${conversationId}/harness/workspace/upload?path=${encodeURIComponent(file.name)}`,
                  { method: "PUT", body: file },
                );
                if (!response.ok) throw new Error("Upload failed / 上传失败");
              }
              await refresh();
            });
            e.target.value = "";
          }}
        />
      </label>
      <button
        onClick={() => {
          const path = prompt("Directory / 目录");
          if (path)
            action(async () => {
              await call("/workspace/directory", "POST", { path });
              await refresh();
            });
        }}
      >
        New folder / 新建目录
      </button>
      {rows(entries)}
      {preview && (
        <dialog open>
          <button onClick={() => setPreview(null)}>Close / 关闭</button>
          <pre>{preview.text ?? JSON.stringify(preview, null, 2)}</pre>
        </dialog>
      )}
    </>
  );
}

function DataPanel({
  call,
  action,
  en,
}: {
  call: Call;
  action: (fn: () => Promise<unknown>) => Promise<void>;
  en: boolean;
}) {
  const [context, setContext] = useState<any>({}),
    [tasks, setTasks] = useState<any[]>([]),
    [plot, setPlot] = useState("table"),
    [x, setX] = useState(""),
    [y, setY] = useState(""),
    [group, setGroup] = useState(""),
    [groupData, setGroupData] = useState<any>(null);
  const refresh = useCallback(async () => {
    setContext(await call("/data/context"));
  }, [call]);
  useEffect(() => {
    refresh().catch(() => {});
    call("/data/discovery-tasks")
      .then((r) => setTasks(r.tasks || []))
      .catch(() => {});
  }, [refresh, call]);
  const columns: string[] = context.preview_columns || context.columns || [],
    data: any[] = context.data || [];
  return (
    <section>
      <div className="toolbar">
        <h2>{en ? "Data workbench" : "数据工作台"}</h2>
        <button onClick={() => action(refresh)}>Refresh / 刷新</button>
        <button
          onClick={() =>
            action(async () => {
              await call("/data/context/reload", "POST", {});
              await refresh();
            })
          }
        >
          Reload context / 加载数据
        </button>
        <button
          onClick={() =>
            action(async () => {
              await call("/data/demo", "POST", { kind: "polynomial" });
              await refresh();
            })
          }
        >
          Demo / 示例
        </button>
      </div>
      <details>
        <summary>Scientific discovery tasks / 天文案例</summary>
        {tasks.map((t) => (
          <article className="card" key={t.name}>
            <strong>{t.title}</strong>
            <p>{en ? t.description_en : t.description_zh}</p>
            <button
              disabled={!t.available}
              onClick={() =>
                action(async () => {
                  await call("/data/discovery-tasks/load", "POST", {
                    name: t.name,
                  });
                  await refresh();
                })
              }
            >
              Load / 加载
            </button>
          </article>
        ))}
      </details>
      <DataVisualization context={context} call={call} />
      <label>
        Structured preview / 结构预览
        <select
          value={group}
          onChange={(e) => {
            setGroup(e.target.value);
            action(async () =>
              setGroupData(
                await call(
                  "/data/context/preview?group=" +
                    encodeURIComponent(e.target.value),
                ),
              ),
            );
          }}
        >
          <option value="">—</option>
          {(context.preview_groups || []).map((g: any) => (
            <option value={g.id} key={g.id}>
              {g.id}
            </option>
          ))}
        </select>
      </label>
      {groupData && (
        <JsonEditor value={groupData} readOnly label="Preview / 预览" />
      )}
      <JsonEditor
        label="Feature / target selection · 变量角色"
        value={{ features: context.features || [], target: context.target }}
        onApply={async (v) => {
          await call("/data/selection", "PUT", v);
          await refresh();
        }}
      />
      <JsonEditor
        label="Variable descriptions / 变量描述"
        value={context.variable_descriptions || {}}
        onApply={async (v) => {
          await call("/data/descriptions", "PUT", { variable_descriptions: v });
          await refresh();
        }}
      />
      <JsonEditor
        label="Heatmap configuration / 热图配置"
        value={{ row: [], column: [], color: "", z: "" }}
        onApply={async (v) =>
          setGroupData(await call("/data/context/heatmap", "POST", v))
        }
      />
    </section>
  );
}

function EvaluatorPanel({
  call,
  action,
}: {
  call: Call;
  action: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [configuration, setConfiguration] = useState<any>({}),
    [source, setSource] = useState(""),
    [result, setResult] = useState<any>(null);
  useEffect(() => {
    call("/evaluator")
      .then((r) => {
        setConfiguration(r);
        setSource(r.source || "");
      })
      .catch(() => {});
  }, [call]);
  return (
    <section>
      <h2>Task & Evaluator / 任务与评测器</h2>
      <label>
        Evaluator / 评测器
        <select
          value={configuration.source_for || configuration.selected || ""}
          onChange={(e) =>
            action(async () => {
              const value = await call(
                "/evaluator?selected=" + encodeURIComponent(e.target.value),
              );
              setConfiguration(value);
              setSource(value.source);
            })
          }
        >
          {[
            ...(configuration.builtins || []),
            ...(configuration.evaluators || []),
            { id: "custom", name: "New custom evaluator / 新建自定义评测器" },
          ].map((item: any) => (
            <option key={item.id} value={item.id}>
              {item.name || item.id}
            </option>
          ))}
        </select>
      </label>
      <JsonEditor
        value={configuration}
        label="Evaluator configuration / 评测配置"
        onApply={async (v) =>
          setConfiguration(await call("/evaluator", "PUT", v))
        }
      />
      <label>
        Python source / 评测器代码
        <textarea
          className="source"
          rows={16}
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
      </label>
      <button
        onClick={() =>
          action(async () =>
            setConfiguration(
              await call("/evaluator", "PUT", {
                selected:
                  configuration.source_for ||
                  configuration.selected ||
                  "custom",
                source,
              }),
            ),
          )
        }
      >
        Save / 保存
      </button>
      <button
        onClick={() =>
          action(async () =>
            setResult(await call("/evaluator/test", "POST", {})),
          )
        }
      >
        Validate / 验证
      </button>
      {result && <JsonEditor value={result} readOnly label="Result / 结果" />}
    </section>
  );
}

function SearchPanel({
  call,
  action,
  snapshot,
  records,
  en,
}: {
  call: Call;
  action: (fn: () => Promise<unknown>) => Promise<void>;
  snapshot: any;
  records: any[];
  en: boolean;
}) {
  const [description, setDescription] = useState(""),
    [prompts, setPrompts] = useState<any>({}),
    [node, setNode] = useState<any>(null);
  return (
    <section>
      <h2>{en ? "Symbolic regression" : "符号回归"}</h2>
      <label>
        Problem / 研究问题
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <button
        onClick={() =>
          action(async () =>
            setPrompts(
              await call("/data/prompts", "POST", {
                problem_description: description,
              }),
            ),
          )
        }
      >
        Preview prompts / 提示词预览
      </button>
      <JsonEditor
        value={prompts}
        label="Prompts / 提示词"
        onApply={async (v) => setPrompts(v)}
      />
      <button
        className="primary"
        disabled={
          !snapshot.context_ready ||
          ["running", "starting"].includes(snapshot.state)
        }
        onClick={() =>
          action(() =>
            call("/start", "POST", {
              problem_description: description,
              ...prompts,
            }),
          )
        }
      >
        Start search / 开始搜索
      </button>
      <div className="toolbar">
        {["next_c", "next_r"].map((c) => (
          <button
            key={c}
            onClick={() =>
              action(() =>
                call("/control/command", "POST", { role: "search", action: c }),
              )
            }
          >
            {c}
          </button>
        ))}
      </div>
      <h3>Search tree / 搜索树</h3>
      <SearchTree
        records={records}
        onSelect={(id) =>
          action(async () =>
            setNode(await call("/records/" + encodeURIComponent(id))),
          )
        }
      />
      {node && (
        <JsonEditor label="Search node / 搜索节点" value={node} readOnly />
      )}
    </section>
  );
}
