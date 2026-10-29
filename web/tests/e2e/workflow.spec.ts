import { expect, test } from "@playwright/test";

test("research workflow uses only the authenticated Next.js backend", async ({
  page,
  context,
}, testInfo) => {
  const remoteRequests: string[] = [];
  page.on("request", (req) => {
    if (!req.url().startsWith("http://localhost:3100"))
      remoteRequests.push(req.url());
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Register / 注册账号" }).click();
  const username = `researcher-${Date.now()}`;
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill("test-password-123456");
  await page.getByRole("button", { name: "注册", exact: true }).click();
  await expect(page.getByText(username, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "模型配置", exact: true }).click();
  await page.getByLabel("Name / 名称").fill("Local test model");
  await page.getByLabel("Provider / 供应商").selectOption("compatible");
  await page.getByLabel("Model / 模型").fill("test-model");
  await page
    .getByLabel("Endpoint", { exact: true })
    .fill("http://mock-provider.test/v1");
  await page.getByLabel("API Key", { exact: true }).fill("a-private-test-key");
  await page.getByLabel("Default / 默认配置").check();
  await page.getByRole("button", { name: "Save / 保存", exact: true }).click();
  await expect(page.getByText("Saved / 已保存", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "工作台", exact: true }).click();
  await page.getByRole("button", { name: "＋ 新建会话" }).click();
  await expect(page.getByRole("heading", { name: "数据工作台" })).toBeVisible();
  await page.locator("input[type=file]").setInputFiles({
    name: "observations.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("x,y\n1,2\n2,4"),
  });
  await expect(
    page.getByRole("button", { name: /observations.csv/ }),
  ).toBeVisible();
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "large-data.csv",
      mimeType: "text/csv",
      buffer: Buffer.alloc(5 * 1024 * 1024, "x"),
    });
  await expect(
    page.getByRole("button", { name: /large-data.csv/ }),
  ).toBeVisible();
  await page.getByLabel("Agent instruction").fill("Prepare the uploaded data");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await page.getByRole("button", { name: "2. 任务与评测器" }).click();
  await page.getByLabel("Agent instruction").fill("Construct an evaluator");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await page.getByRole("button", { name: "3. 符号回归" }).click();
  await page.getByRole("button", { name: "Start search / 开始搜索" }).click();
  await expect(
    page.locator(".candidate-panel").getByText("2*x", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ⅱ pause" }).click();
  await expect(page.locator(".status")).toContainText("paused");
  await page.getByRole("button", { name: "▶ resume" }).click();
  await page.reload();
  await expect(
    page.locator(".candidate-panel").getByText("2*x", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "1. Data preparation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "☾" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({
    path: testInfo.outputPath("workbench-dark.png"),
    fullPage: true,
  });
  const me = await context.request.get("/api/auth/me");
  expect((await me.json()).role).toBe("user");
  expect((await context.request.get("/api/admin/users")).status()).toBe(403);
  expect(
    (
      await context.request.get("/api/conversations/not-owned/harness")
    ).status(),
  ).toBe(404);
  const conversations = (
    await (await context.request.get("/api/conversations")).json()
  ).conversations;
  const first = conversations[0];
  await context.request.patch(`/api/conversations/${first.id}`, {
    headers: { origin: "http://localhost:3100" },
    data: { name: "First study" },
  });
  await page.reload();
  await page.getByRole("button", { name: "＋ New conversation" }).click();
  await expect(page.locator(".conversation")).toHaveCount(2);
  await page.getByRole("button", { name: "First study", exact: true }).click();
  await expect(
    page.locator(".candidate-panel").getByText("2*x", { exact: true }),
  ).toBeVisible();
  await page.locator(".conversation.selected summary").click();
  const downloadEvent = page.waitForEvent("download");
  await page
    .locator(".conversation.selected")
    .getByRole("link", { name: "Export / 导出" })
    .click();
  expect((await downloadEvent).suggestedFilename()).toBe("conversation.zip");
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .locator(".conversation.selected")
    .getByRole("button", { name: "Archive / 归档" })
    .click();
  await expect(
    page.getByRole("button", { name: "First study", exact: true }),
  ).toHaveCount(0);
  expect(remoteRequests).toEqual([]);
});
