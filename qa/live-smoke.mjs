import { request } from "playwright";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { requireEvaluationMode, evaluationSummary } from "./eval-policy.mjs";

if (!process.argv.includes("--live"))
  throw new Error("Run with --live to authorize real API calls.");
const base = process.env.BASE_URL ?? "http://127.0.0.1:8123";
const personal = process.env.EVAL_API_KEY;
if (personal && process.env.EVAL_STORAGE_STATE)
  throw new Error(
    "Use a new temporary provider OR an existing session, not both.",
  );
if (personal && (!process.env.EVAL_BASE_URL || !process.env.EVAL_MODEL))
  throw new Error(
    "EVAL_BASE_URL and EVAL_MODEL are required with EVAL_API_KEY.",
  );
const context = await request.newContext({
  baseURL: base,
  ...(process.env.EVAL_STORAGE_STATE
    ? { storageState: process.env.EVAL_STORAGE_STATE }
    : {}),
  extraHTTPHeaders: {
    "X-Requested-With": "workbench",
    ...(process.env.LIVE_ACCESS_TOKEN
      ? { "X-Live-Access": process.env.LIVE_ACCESS_TOKEN }
      : {}),
  },
});
const report = {
  timestamp: new Date().toISOString(),
  mode: "live",
  status: "running",
  scope:
    "Six live workflow probes on three development scenarios with isolated project histories; not a held-out benchmark or evidence of memory effectiveness. Repair is tested only when natural failures occur.",
  limits: {
    tasks: 6,
    maxRepairsPerTask: 1,
    tokenBudgetPerTask: 24000,
    maxOutputTokensPerCall: 4096,
  },
  results: [],
};
const output = new URL("../evidence/live-smoke.json", import.meta.url);
let temporaryProvider = false,
  started = false;
async function api(path, data) {
  const response =
    data === undefined
      ? await context.get(path)
      : await context.post(path, { data });
  if (!response.ok())
    throw new Error(
      `Workbench API ${path.split("/").at(-1)} failed (HTTP ${response.status()}); response body omitted.`,
    );
  return response.json();
}
async function checkpoint() {
  report.summary = evaluationSummary(report.results);
  await mkdir(new URL("../evidence/", import.meta.url), { recursive: true });
  await writeFile(output, JSON.stringify(report, null, 2) + "\n");
}
try {
  await api("/api/workbench/config");
  if (personal) {
    await api("/api/workbench/provider", {
      enabled: true,
      baseUrl: process.env.EVAL_BASE_URL,
      model: process.env.EVAL_MODEL,
      apiKey: personal,
      inputPrice: 0,
      outputPrice: 0,
    });
    temporaryProvider = true;
  }
  const config = await api("/api/workbench/config");
  requireEvaluationMode(config, true);
  const fixtures = JSON.parse(
    await readFile(new URL("./fixtures.json", import.meta.url), "utf8"),
  )
    .filter((t) => t.split === "dev" && t.memoryStrategy !== "window")
    .slice(0, 6);
  started = true;
  await checkpoint();
  for (const task of fixtures) {
    const project = await api("/api/workbench/projects", {
      name: `Live probe ${task.id} ${Date.now()}`,
    });
    const prefix = `/api/workbench/projects/${project.id}`;
    await api(prefix + "/memories", {
      kind: "constraint",
      key: "项目约束",
      value: "使用中文标题，保留项目进度与任务记录。",
    });
    const submitted = await api(prefix + "/runs", {
      prompt: task.prompt,
      requiredTexts: task.requiredTexts,
      maxRepairs: 1,
      tokenBudget: 24000,
      memoryStrategy: task.memoryStrategy,
      demoFailure: false,
      checkInteraction: true,
    });
    report.pendingRun = { projectId: project.id, runId: submitted.id };
    await checkpoint();
    let run;
    const deadline = Date.now() + 360000;
    while (Date.now() < deadline) {
      const projectState = await api(prefix);
      run = projectState.runs.find((r) => r.id === submitted.id);
      if (run && !["QUEUED", "RUNNING"].includes(run.status)) break;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    if (!run || ["QUEUED", "RUNNING"].includes(run.status))
      throw new Error(
        "Probe timed out; task may still be running. Do not automatically retry.",
      );
    if (run.mode !== "live")
      throw new Error("Unexpected demo result rejected.");
    report.results.push({
      caseId: task.id,
      split: task.split,
      strategy: task.memoryStrategy,
      injectedFailure: false,
      ...run,
    });
    delete report.pendingRun;
    report.model = run.model;
    await checkpoint();
    console.log(
      `${task.id}: ${run.status}, attempts=${run.attempts.length}, usageKnown=${run.usageKnown}`,
    );
    if (run.status === "FAILED" && run.attempts.length === 0)
      throw new Error(
        "Model call failed before producing an artifact; remaining probes stopped.",
      );
  }
  report.status = report.results.every((r) => r.status === "PASSED")
    ? "passed"
    : "completed_with_failures";
  await checkpoint();
  console.log(
    JSON.stringify({
      status: report.status,
      model: report.model,
      summary: report.summary,
    }),
  );
  if (report.status !== "passed") process.exitCode = 1;
} catch (error) {
  if (started) {
    report.status = "incomplete";
    await checkpoint();
  }
  console.error(error.message);
  process.exitCode = 1;
} finally {
  if (temporaryProvider) {
    const removed = await context.delete("/api/workbench/provider");
    if (!removed.ok()) {
      console.error(
        "Temporary provider cleanup failed; remove the isolated test configuration before reuse.",
      );
      process.exitCode = 1;
    }
  }
  await context.dispose();
}
