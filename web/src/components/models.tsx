"use client";
import { useState } from "react";
import { api, type ModelSummary } from "@/lib/client";
const initial = {
  name: "",
  provider: "openrouter",
  model: "",
  endpoint: "",
  api_key: "",
  api_version: "",
  shared: false,
  isDefault: false,
};
export function ModelManager({
  models,
  admin,
  refresh,
}: {
  models: ModelSummary[];
  admin: boolean;
  refresh: () => Promise<void>;
}) {
  const [form, setForm] = useState(initial),
    [editing, setEditing] = useState(""),
    [message, setMessage] = useState("");
  return (
    <section>
      <h2>Model configurations / 模型配置</h2>
      <p>Key 与 Endpoint 成组使用。个人配置失败时不会切换到共享账户。</p>
      {models.map((m) => (
        <article className="card" key={m.id}>
          <strong>{m.name}</strong>
          <span>
            {m.provider} · {m.model} {m.shared ? " · Shared / 共享" : ""}{" "}
            {m.isDefault ? " ★" : ""}
          </span>
          <small>{m.endpoint}</small>
          <button
            disabled={m.shared && !admin}
            onClick={() => {
              setEditing(m.id);
              setForm({
                ...initial,
                ...m,
                api_key: "",
                api_version: m.api_version || "",
              });
            }}
          >
            Edit / 编辑
          </button>
          <button
            disabled={m.shared && !admin}
            onClick={async () => {
              try {
                await api(`models/${m.id}`, "DELETE");
                await refresh();
              } catch (e) {
                setMessage(String(e));
              }
            }}
          >
            Delete / 删除
          </button>
        </article>
      ))}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api(
              editing ? `models/${editing}` : "models",
              editing ? "PUT" : "POST",
              {
                ...form,
                api_key: form.api_key || undefined,
                api_version: form.api_version || undefined,
              },
            );
            setForm(initial);
            setEditing("");
            await refresh();
            setMessage("Saved / 已保存");
          } catch (e) {
            setMessage(String(e));
          }
        }}
      >
        <h3>
          {editing
            ? "Edit configuration / 编辑配置"
            : "Add configuration / 新增配置"}
        </h3>
        <label>
          Name / 名称
          <input
            required
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </label>
        <label>
          Provider / 供应商
          <select
            value={form.provider}
            onChange={(e) => setForm({ ...form, provider: e.target.value })}
          >
            {[
              "openrouter",
              "compatible",
              "azure",
              "openai",
              "deepseek",
              "siliconflow",
              "gemini",
              "lmstudio",
            ].map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Model / 模型
          <input
            required
            value={form.model}
            onChange={(e) => setForm({ ...form, model: e.target.value })}
          />
        </label>
        <label>
          Endpoint
          <input
            type="url"
            value={form.endpoint}
            onChange={(e) => setForm({ ...form, endpoint: e.target.value })}
          />
        </label>
        <label>
          API Key
          <input
            type="password"
            autoComplete="off"
            required={!editing}
            placeholder={
              editing ? "Leave empty to keep current key / 留空保留" : ""
            }
            value={form.api_key}
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
          />
        </label>
        {form.provider === "azure" && (
          <label>
            API Version
            <input
              value={form.api_version}
              onChange={(e) =>
                setForm({ ...form, api_version: e.target.value })
              }
            />
          </label>
        )}
        {admin && (
          <label>
            <input
              type="checkbox"
              checked={form.shared}
              onChange={(e) => setForm({ ...form, shared: e.target.checked })}
            />
            Shared / 发布为共享配置
          </label>
        )}
        <label>
          <input
            type="checkbox"
            checked={form.isDefault}
            onChange={(e) => setForm({ ...form, isDefault: e.target.checked })}
          />
          Default / 默认配置
        </label>
        <button className="primary">Save / 保存</button>
        <button
          type="button"
          onClick={() => {
            setEditing("");
            setForm(initial);
          }}
        >
          Cancel / 取消
        </button>
        <p role="status">{message}</p>
      </form>
    </section>
  );
}
