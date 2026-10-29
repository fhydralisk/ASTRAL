"use client";
import { useEffect, useState } from "react";
import type { Role } from "@/lib/client";
import { JsonEditor } from "./common";

export function AgentSettings({
  role,
  value,
  call,
}: {
  role: Role;
  value: any;
  call: (path: string, method?: string, payload?: unknown) => Promise<any>;
}) {
  const [draft, setDraft] = useState<any>({}),
    [capabilities, setCapabilities] = useState<any>({}),
    [message, setMessage] = useState("");
  const serialized = JSON.stringify(value || {});
  useEffect(() => {
    setDraft(JSON.parse(serialized));
  }, [role, serialized]);
  useEffect(() => {
    call("/capabilities?agent=" + role)
      .then(setCapabilities)
      .catch(() => {});
  }, [role, call]);
  async function save(payload: any) {
    await call(
      role === "search"
        ? "/settings"
        : role === "data"
          ? "/data/agent/settings"
          : "/evaluator/agent/settings",
      role === "search" ? "POST" : "PUT",
      payload,
    );
    setMessage("Saved / 已保存");
  }
  return (
    <details className="settings-form">
      <summary>Agent settings / Agent 设置</summary>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await save(draft);
          } catch (e) {
            setMessage(String(e));
          }
        }}
      >
        <div className="fields">
          {Object.entries({
            llm_max_tokens: "Output token limit / 输出限制",
            ...(role === "search"
              ? {
                  max_restart_loop: "R · Restarts / 重启",
                  global_width: "C · Branches / 分支",
                  max_refinement_depth: "L · Depth / 深度",
                  local_sample_size: "K · Samples / 采样",
                  validation_fraction: "Validation fraction / 验证比例",
                  max_workers: "Tool workers / 工具进程",
                }
              : role === "evaluator"
                ? { max_steps: "Step limit / 步数" }
                : {}),
          }).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                type="number"
                step={key === "validation_fraction" ? "0.01" : "1"}
                min="0"
                value={draft[key] ?? ""}
                onChange={(e) =>
                  setDraft({
                    ...draft,
                    [key]:
                      e.target.value === "" ? null : Number(e.target.value),
                  })
                }
              />
            </label>
          ))}
          <label>
            Tool parser / 工具解析
            <select
              value={draft.tool_parser || "openai"}
              onChange={(e) =>
                setDraft({ ...draft, tool_parser: e.target.value })
              }
            >
              {["openai", "text", "json", "xml"].map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
        </div>
        {(["tools", "skills"] as const).map((kind) => (
          <details key={kind}>
            <summary>
              {kind === "tools" ? "Tools / 工具" : "Skills / 技能"}
            </summary>
            <div className="capabilities">
              {(capabilities[kind] || []).map((item: any) => (
                <label key={item.name} title={item.description}>
                  <input
                    type="checkbox"
                    checked={(
                      draft[kind] ||
                      capabilities["default_" + kind] ||
                      []
                    ).includes(item.name)}
                    onChange={(e) => {
                      const current: string[] =
                        draft[kind] || capabilities["default_" + kind] || [];
                      setDraft({
                        ...draft,
                        [kind]: e.target.checked
                          ? [...current, item.name]
                          : current.filter((n) => n !== item.name),
                      });
                    }}
                  />
                  {item.name}
                </label>
              ))}
            </div>
          </details>
        ))}
        <button>Apply / 应用</button>
        <p role="status">{message}</p>
      </form>
      <JsonEditor
        label="Advanced settings / 高级配置"
        value={value || {}}
        onApply={save}
      />
    </details>
  );
}
