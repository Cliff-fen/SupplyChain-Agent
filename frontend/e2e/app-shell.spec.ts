import { expect, test } from "@playwright/test";

test("login screen is available through the overview deep link", async ({ page }) => {
  await page.goto("/overview");
  await expect(page.locator("h1")).toContainText("把供应链的");
  await expect(page.locator("h1")).toContainText("下一步");
  await expect(page.getByLabel("组织标识")).toBeVisible();
  await expect(page.getByRole("button", { name: "登录工作区" })).toBeEnabled();
  await page.screenshot({ path: "../output/playwright/login-desktop.png", fullPage: true });
});

test("login controls preserve accessible labels", async ({ page }) => {
  await page.goto("/analysis");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await expect(page.getByLabel("登录邮箱")).toHaveValue("admin@demo.local");
  await page.getByLabel("显示密码").click();
  await expect(page.getByLabel("隐藏密码")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "../output/playwright/login-mobile.png", fullPage: true });
});

test("administrator can enter the operations overview", async ({ page }) => {
  await page.goto("/overview");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
  await page.screenshot({ path: "../output/playwright/overview-desktop.png", fullPage: true });
});

test("administrator navigation keeps domain URLs in sync", async ({ page }) => {
  await page.goto("/overview");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible({ timeout: 15_000 });
  const navigation = page.getByRole("navigation", { name: "主导航" });
  await navigation.getByRole("button", { name: /数据源/ }).click();
  await expect(page).toHaveURL(/\/data-sources$/);
  await expect(page.locator("h1", { hasText: "数据源" })).toBeVisible();
  await navigation.getByRole("button", { name: /知识库/ }).click();
  await expect(page).toHaveURL(/\/knowledge$/);
  await expect(page.locator("h1", { hasText: "知识库" })).toBeVisible();
  await navigation.getByRole("button", { name: /报告中心/ }).click();
  await expect(page).toHaveURL(/\/reports$/);
  await expect(page.locator("h1", { hasText: "报告中心" })).toBeVisible();
});

test("mobile navigation prioritizes daily work and exposes enterprise pages through more", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/overview");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  const navigation = page.getByRole("navigation", { name: "移动主导航" });
  await expect(navigation.getByRole("button", { name: "分析会话" })).toBeVisible({ timeout: 15_000 });
  await navigation.getByRole("button", { name: "更多" }).click();
  await page.getByRole("region", { name: "更多工作区功能" }).getByRole("button", { name: "报告中心" }).click();
  await expect(page).toHaveURL(/\/reports$/);
  await expect(page.locator("h1", { hasText: "报告中心" })).toBeVisible();
  await page.screenshot({ path: "../output/playwright/mobile-more-navigation.png", fullPage: true });
});

test("viewer is redirected away from a restricted deep link", async ({ page }) => {
  await page.goto("/audit");
  await page.getByLabel("登录邮箱").fill("viewer@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page).toHaveURL(/\/overview$/, { timeout: 15_000 });
  await expect(page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "组织与审计" })).toHaveCount(0);
});

test("analyst can open analysis resources but cannot enter organization administration", async ({ page }) => {
  await page.goto("/analysis");
  await page.getByLabel("登录邮箱").fill("analyst@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible({ timeout: 15_000 });
  const navigation = page.getByRole("navigation", { name: "主导航" });
  await navigation.getByRole("button", { name: "组织与审计" }).click();
  await expect(page.getByRole("heading", { name: "无权限访问组织与审计" })).toBeVisible();
  await navigation.getByRole("button", { name: /分析会话/ }).click();
  await expect(page.getByLabel("数据源")).toBeEnabled({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "开始分析" })).toBeDisabled();
});

test("second organization only sees its own resources in the browser", async ({ page }) => {
  await page.goto("/data-sources");
  await page.getByLabel("登录邮箱").fill("south-admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-south");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: /数据源/ }).click();
  await expect(page.getByText("南方制造事业部 · POSTGRESQL 演示库")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("示范制造集团 · POSTGRESQL 演示库")).toHaveCount(0);
});

test("organization administrator creates, copies, and revokes an invitation", async ({ page }) => {
  const email = `invite-e2e-${Date.now()}@example.com`;
  await page.goto("/audit");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: "组织与审计" }).click();
  await page.getByLabel("成员邮箱").fill(email);
  await page.getByLabel("成员角色").selectOption("analyst");
  await page.getByRole("button", { name: /发送邀请/ }).click();
  const linkDialog = page.getByRole("dialog", { name: "复制一次性邀请链接" });
  await expect(linkDialog.getByLabel("一次性邀请链接")).toBeVisible({ timeout: 15_000 });
  await linkDialog.getByRole("button", { name: "关闭" }).click();
  await page.getByRole("tab", { name: /邀请管理/ }).click();
  const invitation = page.locator(".invitation-row", { hasText: email });
  await expect(invitation).toBeVisible();
  await invitation.getByRole("button", { name: "撤销邀请" }).click();
  await page.getByRole("button", { name: "确认撤销" }).click();
  await expect(invitation).toContainText("已撤销");
});

test("administrator can inspect the real operational resource paths", async ({ page }) => {
  await page.goto("/overview");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("时间范围").selectOption("7d");
  await expect(page.getByLabel("时间范围")).toHaveValue("7d");
  const navigation = page.getByRole("navigation", { name: "主导航" });
  await navigation.getByRole("button", { name: /数据源/ }).click();
  await page.locator(".datasource-row .row-main-button").first().click();
  await expect(page.locator(".detail-panel h3")).toBeVisible();
  await navigation.getByRole("button", { name: /知识库/ }).click();
  await page.getByRole("button", { name: /管理详情/ }).first().click();
  await expect(page.getByPlaceholder("预览检索，例如：生产达成率口径")).toBeVisible();
  await navigation.getByRole("button", { name: /报告中心/ }).click();
  await page.locator(".list-row .row-main-button").first().click();
  await expect(page.locator(".report-detail")).toBeVisible();
});

test("administrator can retest the repaired local demonstration source", async ({ page }) => {
  await page.goto("/data-sources");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: /数据源/ }).click();
  await page.locator(".datasource-row").filter({ hasText: "POSTGRESQL 演示库" }).getByRole("button", { name: "测试连接" }).click();
  await expect(page.getByRole("status")).toContainText("连接测试通过", { timeout: 15_000 });
});

test("deleting an empty archived knowledge base removes its card immediately", async ({ page }) => {
  const name = `删除回归-${Date.now()}`;
  await page.goto("/knowledge");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: /知识库/ }).click();
  await page.getByLabel("按知识库状态筛选").selectOption("");
  await page.getByLabel("知识库名称", { exact: true }).fill(name);
  await page.getByRole("button", { name: /创建知识库/ }).click();
  await page.getByLabel("按知识库名称筛选").fill(name);
  const card = page.locator(".knowledge-card", { hasText: name });
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button", { name: /管理详情/ }).click();
  await page.getByRole("button", { name: "归档知识库" }).click();
  await page.getByRole("button", { name: "确认归档" }).click();
  await page.getByRole("button", { name: "永久删除空知识库" }).click();
  await page.getByRole("button", { name: "确认永久删除" }).click();
  await expect(card).toHaveCount(0);
});

test("report preview opens the generated PDF in a new window", async ({ page }) => {
  await page.goto("/reports");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: /报告中心/ }).click();
  await expect(page.locator(".report-row-actions").first()).toBeVisible({ timeout: 15_000 });
  const popupPromise = page.waitForEvent("popup");
  await page.locator(".report-row-actions").first().getByRole("button", { name: "预览 PDF" }).click();
  const popup = await popupPromise;
  await expect.poll(() => popup.url(), { timeout: 35_000 }).toMatch(/^blob:/);
  await popup.close();
});

test("analysis history opens inside a contained session window", async ({ page }) => {
  await page.goto("/analysis");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: /分析会话/ }).click();
  const history = page.locator(".analysis-history-row").first();
  await expect(history).toBeVisible({ timeout: 15_000 });
  await history.click();
  const sessionWindow = page.locator(".analysis-session-window");
  await expect(sessionWindow).toBeVisible();
  await expect(sessionWindow.getByText("运行 ID：")).toBeVisible();
  await expect(sessionWindow.getByText(/运行状态：(已完成|运行中|排队中|失败|已取消|已拒绝|等待审批)/)).toBeVisible();
  await expect(sessionWindow.locator(".step-timeline")).toBeVisible();
  await expect(sessionWindow.getByRole("button", { name: "新建会话" })).toHaveCount(0);
});

test("administrator can inspect the enterprise agent control plane", async ({ page }) => {
  await page.goto("/overview");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  const navigation = page.getByRole("navigation", { name: "主导航" });
  await navigation.getByRole("button", { name: "Agent 平台" }).click();
  await expect(page).toHaveURL(/\/agent-platform$/);
  await expect(page.getByRole("heading", { name: "Agent 平台" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "运行观测" })).toBeVisible();
  await page.getByRole("tab", { name: "自进化" }).click();
  await expect(page.getByText("Hermes Evolution Loop")).toBeVisible();
  await expect(page.getByText("自进化护栏")).toBeVisible();
  await page.getByRole("tab", { name: "长期记忆" }).click();
  await expect(page.getByText("用户级长期记忆")).toBeVisible();
  await page.getByRole("tab", { name: "MCP 工具" }).click();
  await expect(page.getByText("受控 MCP Server")).toBeVisible();
  await page.getByRole("tab", { name: "人工审批" }).click();
  await expect(page.getByText("待审批操作", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../output/playwright/agent-platform-desktop.png", fullPage: true });
});

test("mobile navigation opens the enterprise agent control plane", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/overview");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await page.getByRole("navigation", { name: "移动主导航" }).getByRole("button", { name: "更多" }).click();
  await page.getByRole("region", { name: "更多工作区功能" }).getByRole("button", { name: "Agent 平台" }).click();
  await expect(page).toHaveURL(/\/agent-platform$/);
  await expect(page.getByRole("heading", { name: "运行、治理与自进化" })).toBeVisible();
  await page.screenshot({ path: "../output/playwright/agent-platform-mobile.png", fullPage: true });
});

test("administrator receives a streamed terminal state from active resources", async ({ page }) => {
  test.setTimeout(600_000);
  await page.goto("/analysis");
  await page.getByLabel("登录邮箱").fill("admin@demo.local");
  await page.getByLabel("登录密码").fill("ChangeMe123!");
  await page.getByLabel("组织标识").fill("demo-factory");
  await page.getByRole("button", { name: "登录工作区" }).click();
  await expect(page.getByRole("heading", { name: "运营总览" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("navigation", { name: "主导航" }).getByRole("button", { name: /分析会话/ }).click();
  await expect(page.locator("h2", { hasText: "分析会话" })).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("数据源").selectOption({ index: 1 });
  const knowledge = page.getByLabel("知识库");
  const knowledgeId = await knowledge.locator('option').evaluateAll(options =>
    options.map(option => (option as HTMLOptionElement).value).find(Boolean));
  expect(knowledgeId, "A real ingested knowledge base must be available").toBeTruthy();
  await knowledge.selectOption(knowledgeId!);
  await page.getByLabel("分析问题").fill("统计全部工厂所有工单的计划产量、完工产量与生产达成率，并根据知识库说明指标口径。");
  await page.getByRole("button", { name: "开始分析" }).click();
  await expect(page.getByText("实时运行状态")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("任务已创建")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/^(结论已生成|运行失败)$/)).toBeVisible({ timeout: 540_000 });
  await expect(page.getByText(/智能路由|分析完成|分析失败/).first()).toBeVisible();
  await page.screenshot({ path: "../output/playwright/analysis-completed.png", fullPage: true });
});
