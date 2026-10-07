import { executeSteps, ContractError } from "./contract.mjs";
import { chromium } from "playwright";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const task = path.resolve(process.argv[2]);
const html = await readFile(path.join(task, "index.html"), "utf8");
const contract = JSON.parse(
  await readFile(path.join(task, "contract.json"), "utf8"),
);
const errors = [];
let browser;
try {
  browser = await chromium.launch({
    headless: true,
    chromiumSandbox: process.platform === "linux",
    ...(process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : {}),
  });
  // CSP creates an opaque origin and already prevents ServiceWorker registration.
  // Playwright's serviceWorkers:block init script itself throws on such origins.
  const context = await browser.newContext({
    viewport: { width: 1200, height: 800 },
    acceptDownloads: false,
    permissions: [],
  });
  await context.route("**/*", (route) =>
    route.request().url() === "https://workbench.invalid/"
      ? route.fulfill({
          status: 200,
          contentType: "text/html",
          headers: {
            "Content-Security-Policy":
              "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'",
          },
          body: html,
        })
      : route.abort(),
  );
  const page = await context.newPage();
  page.setDefaultTimeout(2500);
  page.on("pageerror", (e) =>
    errors.push("JavaScript error: " + e.message.slice(0, 300)),
  );
  context.on("page", (popup) => {
    if (popup !== page) popup.close().catch(() => {});
  });
  await page.goto("https://workbench.invalid/", {
    waitUntil: "domcontentloaded",
    timeout: 8000,
  });
  if (!(await page.locator("h1").first().isVisible()))
    errors.push("一级标题不可见");
  for (const text of contract.requiredTexts)
    if (!(await page.getByText(text, { exact: false }).first().isVisible()))
      errors.push("验收文本不可见：" + text);
  if (contract.steps?.length) {
    try { await executeSteps(page, contract.steps); }
    catch (error) { errors.push(error instanceof ContractError ? error.message : "结构化交互步骤或断言失败"); }
  } else if (contract.checkInteraction) {
    const button = page.getByTestId("primary-action"),
      result = page.getByTestId("result");
    try {
      const before = (await result.textContent())?.trim();
      await button.click();
      await page.waitForFunction(
        (previous) =>
          document.querySelector("[data-testid=result]")?.textContent?.trim() !==
          previous,
        before,
        { timeout: 2000 },
      );
      if (!(await result.isVisible())) errors.push("交互结果不可见");
    } catch {
      errors.push("点击主按钮后结果未发生可见变化");
    }
  }
  await page.screenshot({
    path: path.join(task, "screenshot.png"),
    fullPage: false,
    timeout: 5000,
  });
  await context.close();
  await writeFile(
    path.join(task, "result.json"),
    JSON.stringify({ errors: [...new Set(errors)] }, null, 2),
  );
} catch (e) {
  console.error("Browser QA infrastructure failure:", e.message);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
