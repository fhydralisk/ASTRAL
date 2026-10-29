"use client";
import { useCallback, useEffect, useState } from "react";
import { api, type Conversation, type ModelSummary } from "@/lib/client";
import { AccountForm, AdminPanel } from "@/components/accounts";
import { ModelManager } from "@/components/models";
import { Workbench } from "@/components/workbench";

export default function Page() {
  const [user, setUser] = useState<any>(null),
    [ready, setReady] = useState(false),
    [creating, setCreating] = useState(false),
    [preferencesReady, setPreferencesReady] = useState(false),
    [en, setEn] = useState(false),
    [dark, setDark] = useState(false),
    [page, setPage] = useState("workbench"),
    [conversations, setConversations] = useState<Conversation[]>([]),
    [selected, setSelected] = useState(""),
    [models, setModels] = useState<ModelSummary[]>([]),
    [message, setMessage] = useState("");
  const notify = useCallback((m: string) => setMessage(m), []);
  useEffect(() => {
    setEn(localStorage.getItem("astral-language") === "en");
    setDark(localStorage.getItem("astral-theme") === "dark");
    setPreferencesReady(true);
    api("auth/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setReady(true));
  }, []);
  useEffect(() => {
    if (!preferencesReady) return;
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    localStorage.setItem("astral-theme", dark ? "dark" : "light");
    document.documentElement.lang = en ? "en" : "zh-CN";
    localStorage.setItem("astral-language", en ? "en" : "zh");
  }, [en, dark, preferencesReady]);
  const refreshConversations = useCallback(async () => {
    const result = await api("conversations");
    setConversations(result.conversations);
    setSelected((previous) => {
      const preferred =
        previous || sessionStorage.getItem("astral-selected-conversation");
      return result.conversations.some((c: Conversation) => c.id === preferred)
        ? preferred
        : result.conversations[0]?.id || "";
    });
  }, []);
  const refreshModels = useCallback(
    async () => setModels((await api("models")).models),
    [],
  );
  useEffect(() => {
    if (user) {
      Promise.all([refreshConversations(), refreshModels()]).catch((e) =>
        setMessage(e.message),
      );
    } else {
      setConversations([]);
      setModels([]);
      setSelected("");
    }
  }, [user, refreshConversations, refreshModels]);
  useEffect(() => {
    if (selected)
      sessionStorage.setItem("astral-selected-conversation", selected);
  }, [selected]);
  const conversation = conversations.find((c) => c.id === selected);
  return (
    <>
      <header>
        <a className="brand" href="/">
          ASTRAL <span>✦</span>
        </a>
        <small>
          {en
            ? "Human–AI interactive astronomy discovery"
            : "人机交互天文发现平台"}
        </small>
        <nav>
          <button onClick={() => setEn(!en)}>{en ? "中文" : "EN"}</button>
          <button onClick={() => setDark(!dark)}>{dark ? "☀" : "☾"}</button>
          {user && (
            <>
              <button onClick={() => setPage("workbench")}>
                {en ? "Workbench" : "工作台"}
              </button>
              <button onClick={() => setPage("models")}>
                {en ? "Models" : "模型配置"}
              </button>
              {user.role === "admin" && (
                <button onClick={() => setPage("admin")}>
                  {en ? "Admin" : "管理"}
                </button>
              )}
              <span>{user.username}</span>
              <button
                onClick={async () => {
                  await api("auth/logout", "POST", {});
                  setUser(null);
                }}
              >
                Logout / 退出
              </button>
            </>
          )}
        </nav>
      </header>
      {message && (
        <div className="notice" role="alert">
          {message}
          <button onClick={() => setMessage("")}>×</button>
        </div>
      )}
      {!ready ? (
        <main>Loading…</main>
      ) : !user ? (
        <AccountForm onLogin={setUser} en={en} />
      ) : page === "models" ? (
        <main className="settings-page">
          <ModelManager
            models={models}
            admin={user.role === "admin"}
            refresh={refreshModels}
          />
        </main>
      ) : page === "admin" ? (
        <main className="settings-page">
          <AdminPanel />
        </main>
      ) : (
        <div className="app-shell">
          <aside className="conversations">
            <h3>{en ? "Conversations" : "研究会话"}</h3>
            <button
              className="primary"
              disabled={creating}
              onClick={async () => {
                setCreating(true);
                try {
                  const next = await api("conversations", "POST", {});
                  await refreshConversations();
                  setSelected(next.id);
                } catch (e) {
                  setMessage(String(e));
                } finally {
                  setCreating(false);
                }
              }}
            >
              ＋ {en ? "New conversation" : "新建会话"}
            </button>
            {conversations.map((c) => (
              <div
                className={
                  "conversation " + (c.id === selected ? "selected" : "")
                }
                key={c.id}
              >
                <button disabled={creating} onClick={() => setSelected(c.id)}>
                  {c.name}
                </button>
                <details>
                  <summary>⋯</summary>
                  <button
                    onClick={async () => {
                      const name = prompt("Name / 名称", c.name);
                      if (name)
                        try {
                          await api(`conversations/${c.id}`, "PATCH", { name });
                          await refreshConversations();
                        } catch (e) {
                          setMessage(String(e));
                        }
                    }}
                  >
                    Rename / 重命名
                  </button>
                  <a href={`/api/conversations/${c.id}/harness/export`}>
                    Export / 导出
                  </a>
                  <button
                    onClick={async () => {
                      if (confirm("Archive / 归档?"))
                        try {
                          await api(`conversations/${c.id}`, "DELETE");
                          await refreshConversations();
                        } catch (e) {
                          setMessage(String(e));
                        }
                    }}
                  >
                    Archive / 归档
                  </button>
                </details>
              </div>
            ))}
          </aside>
          {conversation ? (
            <Workbench
              key={conversation.id}
              conversation={conversation}
              models={models}
              refreshConversations={refreshConversations}
              en={en}
              notify={notify}
            />
          ) : (
            <main className="empty">
              <h1>{en ? "Start a discovery" : "开始一次科学发现"}</h1>
              <p>
                {en
                  ? "Create a conversation and configure a model."
                  : "创建研究会话，并配置共享或个人模型。"}
              </p>
            </main>
          )}
        </div>
      )}
    </>
  );
}
