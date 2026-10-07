import { request } from "playwright";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import { requireEvaluationMode } from "./eval-policy.mjs";
const fixtures = [
 {id:"G-01",prompt:"制作中文研究任务进度页，点击按钮后已完成数量增加。",requiredTexts:["研究任务","项目进度"],steps:[{action:"click",target:"primary-action",value:""},{action:"assert_changed",target:"result",value:""}]},
 {id:"G-02",prompt:"制作中文实验准备清单，先勾选第一项再点击更新，结果精确显示已完成 1 项。",requiredTexts:["实验准备","项目进度"],steps:[{action:"check",target:"selection-item",value:""},{action:"click",target:"primary-action",value:""},{action:"assert_text",target:"result",value:"已完成 1 项"}]},
 {id:"G-03",prompt:"制作中文阅读任务记录页，输入任务内容后提交，结果区域精确显示输入内容。",requiredTexts:["阅读任务","项目进度"],steps:[{action:"fill",target:"task-input",value:"阅读论文"},{action:"click",target:"primary-action",value:""},{action:"assert_text",target:"result",value:"阅读论文"}]}
].flatMap(t=>["graph_single","graph_multi"].map(workflow=>({...t,workflow})));
function summary(rows) {
 return Object.fromEntries(["graph_single","graph_multi"].map(w=>{const r=rows.filter(x=>x.workflow===w);const known=r.every(x=>x.usageKnown);return [w,{tasks:r.length,passed:r.filter(x=>x.status==="PASSED").length,calls:r.reduce((a,x)=>a+x.calls,0),inputTokens:known?r.reduce((a,x)=>a+x.inputTokens,0):null,outputTokens:known?r.reduce((a,x)=>a+x.outputTokens,0):null,meanDurationMs:r.length?r.reduce((a,x)=>a+x.durationMs,0)/r.length:null}]}));
}

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
    "Paired single-role vs planner/coder/reviewer workflows on three development tasks with identical frozen contracts and no retrieval. Not a held-out benchmark; no claim of multi-agent superiority. Maximum 21 provider calls across 6 tasks.",
  limits: {
    tasks: 6,
    maxRepairsPerTask: 1,
    tokenBudgetPerTask: 50000,
    maxOutputTokensPerCall: 4096,
  },
  results: [],
};
const output = new URL("../evidence/graph-live.json", import.meta.url);
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
  report.summary = summary(report.results);
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
      tokenBudget: 50000,
      workflow: task.workflow,
      steps: task.steps,
      pauseAfterPlan: task.id === "G-01" && task.workflow === "graph_multi",
      memoryStrategy: "none",
      demoFailure: false,
      checkInteraction: true,
    });
    report.pendingRun = { projectId: project.id, runId: submitted.id };
    await checkpoint();
    let run;
    let resumed = false;
    const deadline = Date.now() + 900000;
    while (Date.now() < deadline) {
      const projectState = await api(prefix);
      run = projectState.runs.find((r) => r.id === submitted.id);
      if (run?.status === "AWAITING_APPROVAL" && !resumed) {
        report.approvalCheckpoint = {runId:run.id,calls:run.calls,contractHash:run.contractHash};
        await checkpoint();await api(prefix+"/runs/"+run.id+"/resume",{});resumed=true;continue;
      }
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
      workflow: task.workflow,
      strategy: "none",
      injectedFailure: false,
      ...run,
    });
    delete report.pendingRun;
    report.model = run.model;
    await checkpoint();
    console.log(
      `${task.id}/${task.workflow}: ${run.status}, attempts=${run.attempts.length}, usageKnown=${run.usageKnown}`,
    );
    if (["FAILED","INTERRUPTED","BUDGET_EXCEEDED"].includes(run.status) && run.attempts.length === 0)
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
