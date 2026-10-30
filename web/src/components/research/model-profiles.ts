import { api, type ModelSummary, type Role } from "@/lib/client";

/** Retain the three original settings dialogs; replace only their credential fields. */
export function modelProfiles(
  root: HTMLElement,
  selected: () => string,
  manage: () => void,
) {
  const inputs: Record<Role, string[]> = {
    search: ["provider", "model", "api-key"],
    data: ["data-provider", "data-model", "data-api-key", "data-proxy"],
    evaluator: [
      "evaluator-agent-provider",
      "evaluator-agent-model",
      "evaluator-agent-api-key",
      "evaluator-agent-proxy",
    ],
  };
  return async (role: Role) => {
    if (!selected()) return;
    const [{ models }, { conversations }] = await Promise.all([
      api("models"),
      api("conversations"),
    ]);
    if (!root.isConnected) return;
    const conversation = conversations.find((c: any) => c.id === selected());
    const first = root
      .querySelector<HTMLElement>(`#${inputs[role][0]}`)
      ?.closest("label");
    if (!first) return;
    for (const id of inputs[role]) {
      const input = root.querySelector<HTMLInputElement>(`#${id}`);
      if (input) {
        input.disabled = true;
        const field = input.closest<HTMLElement>("label,.settings-field");
        if (field) field.hidden = true;
      }
    }
    let host = root.querySelector<HTMLElement>(`#${role}-profile-field`);
    if (!host) {
      host = document.createElement("div");
      host.id = `${role}-profile-field`;
      host.className = "profile-field";
      first.before(host);
    }
    host.replaceChildren();
    const label = document.createElement("label"),
      title = document.createElement("span"),
      select = document.createElement("select"),
      summary = document.createElement("small"),
      button = document.createElement("button");
    const en = document.documentElement.lang === "en";
    title.textContent = en ? "Model configuration" : "模型配置";
    select.id = `${role}-model-profile`;
    select.setAttribute("aria-label", `${role} model configuration`);
    select.add(
      new Option(
        en
          ? "Default (personal override / shared default)"
          : "默认（个人覆盖 / 共享默认）",
        "",
      ),
    );
    for (const model of models as ModelSummary[])
      select.add(
        new Option(
          `${model.name} · ${model.model}${model.shared ? (en ? " · Shared" : " · 共享") : ""}`,
          model.id,
        ),
      );
    select.value = conversation?.models?.[role] || "";
    function describe() {
      const current =
        models.find((m: any) => m.id === select.value) ||
        models.find((m: any) => m.isDefault && !m.shared) ||
        models.find((m: any) => m.isDefault && m.shared);
      summary.textContent = current
        ? `${current.provider} · ${current.model} · ${current.endpoint || "Default endpoint"}`
        : en
          ? "Configure a model before running."
          : "请先添加个人模型配置，或使用管理员发布的共享配置。";
    }
    select.onchange = async () => {
      select.disabled = true;
      try {
        await api(`conversations/${selected()}`, "PATCH", {
          models: { ...conversation.models, [role]: select.value },
        });
        describe();
      } catch (error) {
        summary.textContent = String(error);
      } finally {
        select.disabled = false;
      }
    };
    button.type = "button";
    button.textContent = en ? "Manage model configurations" : "管理模型配置";
    button.onclick = manage;
    label.append(title, select);
    host.append(label, summary, button);
    describe();
  };
}
