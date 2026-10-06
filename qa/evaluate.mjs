import { request } from "playwright";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { requireEvaluationMode } from "./eval-policy.mjs";
const base = process.env.BASE_URL ?? "http://127.0.0.1:8123";
const context = await request.newContext({
  baseURL: base,
  extraHTTPHeaders: {
    "X-Requested-With": "workbench",
    ...(process.env.LIVE_ACCESS_TOKEN
      ? { "X-Live-Access": process.env.LIVE_ACCESS_TOKEN }
      : {}),
  },
});
const config = await (await context.get("/api/workbench/config")).json();
requireEvaluationMode(config, process.argv.includes("--live"));
const fixtures = JSON.parse(
  await readFile(new URL("./fixtures.json", import.meta.url), "utf8"),
);
const project = await (
  await context.post("/api/workbench/projects", {
    data: { name: `Evaluation ${config.mode} ${Date.now()}` },
  })
).json();
const prefix = `/api/workbench/projects/${project.id}`;
await context.post(prefix + "/memories", {
  data: {
    kind: "constraint",
    key: "项目约束",
    value: "使用中文标题，保留项目进度与任务记录。",
  },
});
const results = [];
for (const task of fixtures) {
  const response = await context.post(prefix + "/runs", {
    data: {
      prompt: task.prompt,
      requiredTexts: task.requiredTexts,
      maxRepairs: 2,
      tokenBudget: 24000,
      memoryStrategy: task.memoryStrategy,
      demoFailure: task.injectFailure,
      checkInteraction: true,
    },
  });
  if (!response.ok()) throw Error(await response.text());
  const submitted = await response.json();
  let run,
    deadline = Date.now() + 360000;
  while (Date.now() < deadline) {
    const p = await (await context.get(prefix)).json();
    run = p.runs.find((r) => r.id === submitted.id);
    if (!["QUEUED", "RUNNING"].includes(run.status)) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (!run || ["QUEUED", "RUNNING"].includes(run.status))
    throw Error("Evaluation timed out");
  results.push({
    caseId: task.id,
    split: task.split,
    strategy: task.memoryStrategy,
    injectedFailure: task.injectFailure,
    ...run,
  });
  console.log(`${task.id}: ${run.status} / ${run.attempts.length} attempts`);
}
const summarize = (rows) => ({
  count: rows.length,
  firstPass: rows.filter((r) => r.attempts[0]?.browserStatus === "PASSED")
    .length,
  finalPass: rows.filter((r) => r.status === "PASSED").length,
  meanAttempts: rows.reduce((s, r) => s + r.attempts.length, 0) / rows.length,
  meanDurationMs: rows.reduce((s, r) => s + r.durationMs, 0) / rows.length,
});
const report = {
  timestamp: new Date().toISOString(),
  mode: config.mode,
  scope:
    config.mode === "demo"
      ? "Deterministic fixtures test workflow behavior, NOT model quality or memory effectiveness."
      : "Live model evaluation on small development/held-out task sets; not a public benchmark.",
  model: results[0]?.model,
  summary: summarize(results),
  splits: Object.fromEntries(
    ["dev", "test"].map((s) => [
      s,
      summarize(results.filter((r) => r.split === s)),
    ]),
  ),
  results,
};
await mkdir("../evidence", { recursive: true });
await writeFile(
  `../evidence/evaluation-${config.mode}.json`,
  JSON.stringify(report, null, 2),
);
console.log(JSON.stringify(report.summary));
await context.dispose();
