"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/client";
export function AccountForm({
  onLogin,
  en,
}: {
  onLogin: (u: any) => void;
  en: boolean;
}) {
  const [register, setRegister] = useState(false),
    [mode, setMode] = useState("open"),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [invitation, setInvitation] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api("auth/mode")
      .then((r) => setMode(r.mode))
      .catch((e) => setError(e.message));
    setInvitation(new URLSearchParams(location.search).get("invitation") || "");
  }, []);
  return (
    <main className="account">
      <h1>
        ASTRAL<span>✦</span>
      </h1>
      <p>
        {en
          ? "Human–AI interactive astronomy discovery"
          : "人机交互天文发现平台"}
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            if (register)
              await api("auth/register", "POST", {
                username,
                password,
                invitation,
              });
            onLogin(await api("auth/login", "POST", { username, password }));
          } catch (e) {
            setError(String(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>
          {register
            ? en
              ? "Create account"
              : "创建账号"
            : en
              ? "Sign in"
              : "登录"}
        </h2>
        <label>
          {en ? "Username" : "用户名"}
          <input
            autoComplete="username"
            required
            minLength={3}
            maxLength={64}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </label>
        <label>
          {en ? "Password" : "密码"}
          <input
            type="password"
            autoComplete={register ? "new-password" : "current-password"}
            required
            minLength={register ? 12 : 1}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {register && mode === "invite" && (
          <label>
            Invitation / 邀请码
            <input
              required
              value={invitation}
              onChange={(e) => setInvitation(e.target.value)}
            />
          </label>
        )}
        <button className="primary" disabled={busy}>
          {busy
            ? "…"
            : register
              ? en
                ? "Register"
                : "注册"
              : en
                ? "Sign in"
                : "登录"}
        </button>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        {mode !== "admin" && (
          <button
            type="button"
            className="link"
            onClick={() => setRegister(!register)}
          >
            {register ? "Sign in / 已有账号" : "Register / 注册账号"}
          </button>
        )}
      </form>
    </main>
  );
}
export function AdminPanel() {
  const [mode, setMode] = useState("open"),
    [users, setUsers] = useState<any[]>([]),
    [message, setMessage] = useState(""),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState("");
  async function refresh() {
    setUsers((await api("admin/users")).users);
    setMode((await api("admin/registration")).mode);
  }
  useEffect(() => {
    refresh().catch((e) => setMessage(e.message));
  }, []);
  async function action(fn: () => Promise<unknown>) {
    try {
      await fn();
      await refresh();
      setMessage("Saved / 已保存");
    } catch (e) {
      setMessage(String(e));
    }
  }
  return (
    <section>
      <h2>Administration / 管理</h2>
      <label>
        Registration / 注册模式
        <select
          value={mode}
          onChange={(e) =>
            action(() =>
              api("admin/registration", "PUT", { mode: e.target.value }),
            )
          }
        >
          <option value="open">Open / 开放</option>
          <option value="invite">Invite / 邀请</option>
          <option value="admin">Admin-created / 管理员创建</option>
        </select>
      </label>
      <button
        onClick={async () => {
          try {
            const result = await api("admin/invitations", "POST", {});
            setMessage(`${location.origin}/?invitation=${result.token}`);
          } catch (e) {
            setMessage(String(e));
          }
        }}
      >
        Create invitation / 创建邀请
      </button>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          action(async () => {
            await api("admin/users", "POST", { username, password });
            setUsername("");
            setPassword("");
          });
        }}
      >
        <h3>Create user / 创建用户</h3>
        <input
          placeholder="username"
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          type="password"
          placeholder="password (12+)"
          required
          minLength={12}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button>Create / 创建</button>
      </form>
      <p role="status">{message}</p>
      {users.map((u) => (
        <article className="card" key={u.id}>
          <strong>{u.username}</strong> · {u.role}
          {u.role !== "admin" && (
            <>
              <button
                onClick={() =>
                  action(() =>
                    api(`admin/users/${u.id}`, "PATCH", {
                      disabled: !u.disabled,
                    }),
                  )
                }
              >
                {u.disabled ? "Enable / 启用" : "Disable / 禁用"}
              </button>
              <button
                onClick={() => {
                  const next = prompt("New password (12+ characters)");
                  if (next)
                    action(() =>
                      api(`admin/users/${u.id}`, "PATCH", { password: next }),
                    );
                }}
              >
                Reset password / 重置密码
              </button>
            </>
          )}
        </article>
      ))}
    </section>
  );
}
