import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import assert from "node:assert/strict";
const base = process.env.BASE_URL ?? "http://127.0.0.1:8123";
const browser = await chromium.launch({ headless: true,
  args: process.env.TEST_TLS_SPKI ? [`--ignore-certificate-errors-spki-list=${process.env.TEST_TLS_SPKI}`] : [] });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1080 },
});
const page = await context.newPage(),
  failures = [];
page.on("pageerror", (e) => failures.push(e.message));
await mkdir("test-results", { recursive: true });
try {
  await page.goto(base);
  await page.getByRole("button", { name: "创建我的项目" }).click();
  await page.getByText("＋ 添加或更新记忆").click();
  await page.getByRole("button", { name: "保存记忆", exact: true }).click();
  await page
    .getByText("简洁、绿色主题，适合研究项目展示", { exact: true })
    .waitFor();
  await page.getByLabel("演示一次交互失败，再自动修复").check();
  await page.getByRole("button", { name: /开始生成与验证/ }).click();
  await page
    .getByText("浏览器验收通过", { exact: true })
    .waitFor({ timeout: 60000 });
  await page.getByRole("button", { name: "过程", exact: true }).click();
  await page
    .getByText("点击主按钮后结果未发生可见变化", { exact: true })
    .waitFor();
  await page.screenshot({ path: "test-results/workflow.png", fullPage: true });
  await page.getByRole("button", { name: "预览", exact: true }).click();
  await page.frameLocator("iframe").locator("h1").waitFor();
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: "test-results/desktop.png", fullPage: true });
  await page.getByRole("button", { name: /项目知识/ }).click();
  await page.getByLabel("文档标题").fill("研究项目说明");
  await page
    .getByLabel("文档内容")
    .fill("目标用户是认知神经科学研究生。项目需要记录实验进度并生成开发汇报。");
  await page.getByRole("button", { name: "保存资料", exact: true }).click();
  await page.getByLabel("检索问题").fill("目标用户");
  await page.getByRole("button", { name: /查找依据/ }).click();
  await page
    .getByText("目标用户是认知神经科学研究生。", { exact: true })
    .waitFor();
  await page.getByRole("button", { name: /汇报助手/ }).click();
  await page.getByRole("button", { name: "生成汇报", exact: true }).click();
  await page.locator("pre.report").filter({ hasText: "PASSED" }).waitFor();
  const own = await context.request.get(base + "/api/workbench/projects");
  const projects = await own.json(),
    p = projects[0],
    run = p.runs[0];
  assert.equal(run.attempts.length, 2);
  assert.equal(run.attempts[0].browserStatus, "FAILED");
  assert.equal(run.attempts[1].browserStatus, "PASSED");
  assert.equal(run.mode, "demo");
  assert.equal(run.estimatedCost, 0);
  assert.equal(run.memorySources.length, 1);
  const isolated = await browser.newContext();
  assert.equal(
    (
      await isolated.request.get(`${base}/api/workbench/projects/${p.id}`)
    ).status(),
    404,
  );
  await isolated.close();
  assert.equal(
    (
      await context.request.post(`${base}/api/workbench/projects`, {
        data: { name: "csrf" },
      })
    ).status(),
    403,
  );
  assert.equal(
    (
      await context.request.post(`${base}/api/workbench/projects`, {
        headers: { "X-Requested-With": "workbench" },
        data: { name: "x".repeat(140000) },
      })
    ).status(),
    413,
  );
  await page.getByRole("button", { name: /应用工坊/ }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.frameLocator("iframe").locator("h1").waitFor();
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "mobile page must not overflow",
  );
  assert.deepEqual(failures, []);
  await writeFile(
    "test-results/smoke.json",
    JSON.stringify(
      {
        passed: true,
        checks: [
          "failure detected",
          "repair verified",
          "memory used",
          "document retrieval",
          "report export",
          "cross-owner isolation",
          "CSRF rejection",
          "oversized request rejected",
          "mobile overflow",
          "no console errors",
        ],
        runId: run.id,
        mode: run.mode,
      },
      null,
      2,
    ),
  );
  console.log(
    "Browser smoke passed: repair, memory, knowledge, report, isolation, CSRF and responsive layout.",
  );
} finally {
  await browser.close();
}
