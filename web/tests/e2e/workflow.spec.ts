import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

async function register(page: any) {
  await page.goto("/");
  await page.getByRole("button", { name: "Register / 注册账号" }).click();
  await page
    .getByLabel("用户名", { exact: true })
    .fill(`researcher-${Date.now()}`);
  await page.getByLabel("密码", { exact: true }).fill("test-password-123456");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await expect(page.locator("html")).toHaveClass(/ui-ready/);
  await expect(page.locator("#connection")).not.toHaveText("连接错误");
}

test("original workflow: models, uploads, agents, evaluator, search, tree, sessions and export", async ({
  page,
  context,
}, info) => {
  const errors: string[] = [],
    remote: string[] = [],
    reloads: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (r.url().includes("/harness/data/context/reload")) reloads.push(r.url());
    if (!r.url().startsWith("http://localhost:3100")) remote.push(r.url());
  });
  await register(page);
  await page.locator("#account-settings").click();
  await page.getByLabel("Name / 名称").fill("Local model");
  await page.getByLabel("Provider / 供应商").selectOption("compatible");
  await page.getByLabel("Model / 模型").fill("test-model");
  await page
    .getByLabel("Endpoint", { exact: true })
    .fill("http://model.test/v1");
  await page.getByLabel("API Key", { exact: true }).fill("test-key");
  await page.getByLabel("Default / 默认").check();
  await page.getByRole("button", { name: "Save / 保存", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Saved / 已保存");
  await page.getByRole("button", { name: "Close account settings" }).click();
  await page.locator("#data-agent-settings-toggle").click();
  await expect(page.locator("#data-model-profile")).toBeVisible();
  expect(reloads).toEqual([]);
  await expect(page.locator("#data-api-key")).not.toBeVisible();
  await page.locator("#data-settings-cancel").click();
  await page.locator("#data-file-input").setInputFiles({
    name: "observations.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("x,y\n1,2\n2,4"),
  });
  await expect(page.locator("#files")).toContainText("observations.csv");
  await page.locator("#file-input").setInputFiles({
    name: "large.bin",
    mimeType: "application/octet-stream",
    buffer: Buffer.alloc(5 * 1024 * 1024, "x"),
  });
  await expect(page.locator("#files")).toContainText("large.bin");
  await page.locator("#data-agent-input").fill("Prepare the uploaded data");
  await page.locator("#data-agent-send").click();
  await expect(page.locator("#data-agent-feed")).toContainText(
    "Task completed",
  );
  await page.locator("#data-tab").click();
  await expect(page.locator("#evaluator-code")).toBeVisible();
  await page.locator("#evaluator-select").selectOption("observational");
  await expect(page.locator("#evaluator-select")).toHaveValue("observational");
  await page.locator("#evaluator-agent-toggle").click();
  await page.locator("#evaluator-agent-input").fill("Construct an evaluator");
  await page.locator("#evaluator-agent-send").click();
  await expect(page.locator("#evaluator-agent-feed")).toContainText(
    "Task completed",
  );
  await page.locator("#timeline-tab").click();
  await page.locator("#prompt").fill("Find an interpretable formula");
  await page.locator("#send").click();
  await expect(page.locator("#topk")).toContainText("2");
  await expect(page.locator("#tree")).toHaveAttribute(
    "src",
    /viewer.*conversation=/,
  );
  await expect(
    page.frameLocator("#tree").locator("#graph .node"),
  ).not.toHaveCount(0);
  await page.locator("#send").click();
  await expect(page.locator("#status")).toContainText("暂停");
  await page.locator("#prompt").fill("Continue the search");
  await page.locator("#send").click();
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/ui-ready/);
  await expect(page.locator("#topk")).toContainText("2");
  await page.locator("#left-resizer .panel-toggle").click();
  await expect(page.locator("main").first()).toHaveClass(/left-collapsed/);
  await page.locator("#left-resizer .panel-toggle").click();
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.locator("#language-toggle").click();
  await expect(page.locator("#prepare-tab")).toHaveText("Data Preparation");
  await page.screenshot({
    path: info.outputPath("restored-workbench-dark.png"),
    fullPage: true,
  });
  const conversations = (
    await (await context.request.get("/api/conversations")).json()
  ).conversations;
  const first = conversations[0];
  await context.request.patch(`/api/conversations/${first.id}`, {
    headers: { origin: "http://localhost:3100" },
    data: { name: "First study" },
  });
  await page.reload();
  await page.locator("#conversations-panel-tab").click();
  await Promise.all([
    page.waitForEvent("load"),
    page.locator("#new-conversation").click(),
  ]);
  await expect(page.locator("html")).toHaveClass(/ui-ready/);
  await page.locator("#conversations-panel-tab").click();
  await Promise.all([
    page.waitForEvent("load"),
    page
      .locator(".conversation-item")
      .filter({ hasText: "First study" })
      .click(),
  ]);
  await expect(page.locator("#topk")).toContainText("2");
  await page.locator("#conversations-panel-tab").click();
  await page.locator(".conversation-row.active summary").click();
  const downloaded = page.waitForEvent("download");
  await page
    .locator(".conversation-row.active .conversation-item-menu a")
    .click();
  expect((await downloaded).suggestedFilename()).toBe("conversation.zip");
  await page.locator(".conversation-row.active summary").click();
  await Promise.all([
    page.waitForEvent("load"),
    page
      .locator(".conversation-row.active .conversation-archive-action")
      .click(),
  ]);
  await page.locator("#conversations-panel-tab").click();
  await expect(page.locator("#conversations")).not.toContainText("First study");
  expect(
    (
      await context.request.get(
        `/api/conversations/not-owned/harness/control/events/1`,
      )
    ).status(),
  ).toBe(404);
  expect(errors).toEqual([]);
  expect(remote).toEqual([]);
});

test("original reference and React migration retain the same layout and phase surfaces", async ({
  page,
  context,
}, info) => {
  await register(page);
  const reference = await context.newPage();
  const fixture = "tests/fixtures/original/";
  const [markup, css, script] = await Promise.all(
    ["platform-markup.html", "platform.css", "platform-controller.js"].map(
      (f) => readFile(fixture + f, "utf8"),
    ),
  );
  // Presentation reference only; it cannot reach any legacy backend or scientific process.
  await reference.route("**/api/**", async (route) => {
    const req = route.request(),
      url = new URL(req.url());
    const path = url.pathname;
    const data =
      path === "/api/conversations"
        ? {
            selected: "reference",
            conversations: [
              { id: "reference", name: "Reference", updated_at: "2026-01-01" },
            ],
          }
        : path === "/api/version"
          ? { version: "reference" }
          : path.includes("capabilities")
            ? { tools: [], skills: [], default_tools: [], default_skills: [] }
            : path.includes("events")
              ? { events: [] }
              : path.includes("workspace")
                ? { entries: [] }
                : path.includes("provider-credential")
                  ? { configured: false, env_var: "API_KEY" }
                  : path.includes("evaluator")
                    ? {
                        selected: "default",
                        source: "# evaluator",
                        editable: true,
                        settings: {},
                      }
                    : path.includes("context")
                      ? { columns: [], data: [] }
                      : {
                          state: "idle",
                          settings: {},
                          data_agent_settings: {},
                          topk_records: [],
                        };
    await route.fulfill({ json: data });
  });
  await reference.route("**/reference", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="theme-color" content="#1F2C7E"><style>${css}</style></head><body>${markup}<script>${script}</script></body></html>`,
    }),
  );
  await reference.goto("/reference");
  await expect(reference.locator("html")).toHaveClass(/ui-ready/);
  const boxes = async (p: any) =>
    p.evaluate(() =>
      Object.fromEntries(
        [
          "workspace",
          "left-resizer",
          "data-preparation",
          "insights-panel",
          "right-resizer",
          "prepare-tab",
          "data-tab",
          "timeline-tab",
        ].map((id) => {
          const r = document.getElementById(id)!.getBoundingClientRect();
          return [id, [r.x, r.y, r.width, r.height]];
        }),
      ),
    );
  expect(await boxes(page)).toEqual(await boxes(reference));
  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(viewport);
    await reference.setViewportSize(viewport);
    for (const surface of [page, reference])
      await surface.evaluate(
        () =>
          new Promise<void>((resolve) =>
            requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
          ),
      );
    expect(await boxes(page)).toEqual(await boxes(reference));
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await reference.setViewportSize({ width: 1280, height: 720 });
  for (const tab of ["data", "timeline", "prepare"]) {
    await page.locator(`#${tab}-tab`).click();
    await reference.locator(`#${tab}-tab`).click();
    const visible = async (p: any) =>
      p.evaluate(() =>
        Object.fromEntries(
          [
            "data-preparation",
            "data-setup",
            "search-insights",
            "data-insights",
            "composer",
          ].map((id) => [id, !document.getElementById(id)!.hidden]),
        ),
      );
    expect(await visible(page)).toEqual(await visible(reference));
  }
  await page.screenshot({
    path: info.outputPath("react-original-layout.png"),
    fullPage: true,
  });
  await reference.screenshot({
    path: info.outputPath("main-original-layout.png"),
    fullPage: true,
  });
  await reference.close();
});
