import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import assert from "node:assert/strict";
const base = process.env.BASE_URL ?? "http://127.0.0.1:8123";
const browser = await chromium.launch({ headless: true,
  args: process.env.TEST_TLS_SPKI ? [`--ignore-certificate-errors-spki-list=${process.env.TEST_TLS_SPKI}`] : [] });
const context = await browser.newContext({
  viewport: { width: 1440, height: 1080 },
});
const page = await context.newPage();
const failures = [];
page.on("pageerror", (e) => failures.push(e.message));
const endpoint = base + "/api/workbench/provider";
const headers = { "X-Requested-With": "workbench" };
const fakeKey = "fake-smoke-key-never-call-a-provider-1234";
await mkdir("test-results", { recursive: true });
try {
  await page.goto(base);
  await page.getByRole("button", { name: /模型配置/ }).click();
  await page.getByLabel("模型名称", { exact: true }).fill("my-custom-model");
  await page.locator("#provider-key").fill(fakeKey);
  await page.getByRole("button", { name: "保存模型配置", exact: true }).click();
  await page
    .getByRole("status")
    .filter({ hasText: "配置已保存，后续生成将使用你的模型。" })
    .waitFor();
  assert.equal(await page.locator("#provider-key").inputValue(), "");
  const response = await context.request.get(endpoint);
  assert.equal(response.headers()["cache-control"], "no-store");
  const saved = await response.json();
  assert.equal(saved.enabled, true);
  assert.equal(saved.hasKey, true);
  assert.equal(saved.model, "my-custom-model");
  assert.equal(JSON.stringify(saved).includes(fakeKey), false);
  assert.equal(saved.keyMask, "••••••••1234");
  const config = await (
    await context.request.get(base + "/api/workbench/config")
  ).json();
  assert.equal(config.mode, "live");
  assert.equal(config.providerSource, "personal");
  assert.equal(config.liveAccessRequired, false);
  await page.reload();
  await page.getByRole("button", { name: /模型配置/ }).click();
  await page.getByText("已保存 ••••••••1234", { exact: true }).waitFor();
  assert.equal(
    await page.getByLabel("模型名称", { exact: true }).inputValue(),
    "my-custom-model",
  );
  assert.equal(await page.locator("#provider-key").inputValue(), "");
  assert.equal(
    await page.evaluate(() =>
      Object.values(localStorage).join("").includes("fake-smoke-key"),
    ),
    false,
  );
  const isolated = await browser.newContext();
  const other = await (await isolated.request.get(endpoint)).json();
  assert.equal(other.hasKey, false);
  assert.equal(other.enabled, false);
  await isolated.close();
  const noCsrf = await context.request.post(endpoint, {
    data: {
      enabled: true,
      baseUrl: "https://api.deepseek.com/v1",
      model: "x",
      apiKey: fakeKey,
    },
  });
  assert.equal(noCsrf.status(), 403);
  const unsafe = await context.request.post(endpoint, {
    headers,
    data: {
      enabled: true,
      baseUrl: "http://127.0.0.1:8123",
      model: "x",
      apiKey: fakeKey,
    },
  });
  assert.equal(unsafe.status(), 400);
  await page.screenshot({
    path: "test-results/model-settings.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/model-settings-mobile.png",
    fullPage: true,
  });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
    "mobile layout must not overflow",
  );
  await page.getByLabel("启用我的模型用于生成").uncheck();
  await page.getByRole("button", { name: "保存模型配置", exact: true }).click();
  await page
    .getByRole("status")
    .filter({ hasText: "个人模型暂未启用" })
    .waitFor();
  const disabled = await (await context.request.get(endpoint)).json();
  assert.equal(disabled.enabled, false);
  assert.equal(disabled.hasKey, true);
  assert.equal(
    (await (await context.request.get(base + "/api/workbench/config")).json())
      .mode,
    "demo",
  );
  await page.getByRole("button", { name: "清除模型配置", exact: true }).click();
  await page.getByRole("status").filter({ hasText: "已清除" }).waitFor();
  assert.equal(
    (await (await context.request.get(endpoint)).json()).hasKey,
    false,
  );
  const noConfigTest = await context.request.post(endpoint + "/test", {
    headers,
    data: {},
  });
  assert.equal(noConfigTest.status(), 400);
  assert.deepEqual(failures, []);
  const evidence = {
    verifiedAt: new Date().toISOString(),
    status: "passed",
    checks: [
      "save",
      "masked response",
      "no-store",
      "reload persistence",
      "owner isolation",
      "csrf",
      "endpoint restrictions",
      "disable with key retained",
      "clear",
      "mobile layout",
    ],
    externalProviderCalls: 0,
  };
  await writeFile(
    "test-results/provider-smoke.json",
    JSON.stringify(evidence, null, 2) + "\n",
  );
  console.log(JSON.stringify(evidence));
} finally {
  await context.request.delete(endpoint, { headers });
  await browser.close();
}
