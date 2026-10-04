<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import type { Project, Config, Source } from "./types";
const projects = ref<Project[]>([]),
  current = ref<Project | null>(null),
  config = ref<Config | null>(null);
const tab = ref("studio"),
  error = ref(""),
  busy = ref(false),
  name = ref(""),
  prompt = ref("为我的研究项目制作一个任务进度页面");
const required = ref("项目进度\n研究任务"),
  strategy = ref("retrieval"),
  maxRepairs = ref(2),
  injectFailure = ref(false),
  interaction = ref(true);
const key = ref("设计风格"),
  value = ref("简洁、绿色主题，适合研究项目展示"),
  kind = ref("constraint");
const docTitle = ref("项目说明"),
  docContent = ref(""),
  query = ref(""),
  answer = ref(""),
  sources = ref<Source[]>([]);
const report = ref(""),
  selectedRun = ref(""),
  previewTab = ref("preview"),
  access = ref(""),
  documentFile = ref<HTMLInputElement>();
const tabs = [
  { id: "studio", label: "应用工坊", icon: "◈" },
  { id: "knowledge", label: "项目知识", icon: "⌕" },
  { id: "report", label: "汇报助手", icon: "▤" },
  { id: "metrics", label: "运行评测", icon: "▥" },
];
const activeRun = computed(
  () =>
    current.value?.runs.find((r) => r.id === selectedRun.value) ??
    current.value?.runs.at(-1),
);
const running = computed(
  () =>
    current.value?.runs.some((r) => ["QUEUED", "RUNNING"].includes(r.status)) ??
    false,
);
const activeMemories = computed(
  () => current.value?.memories.filter((m) => m.active) ?? [],
);
const artifactUrl = computed(() =>
  current.value && activeRun.value?.attempts.length
    ? `/api/workbench/projects/${current.value.id}/runs/${activeRun.value.id}/artifact`
    : "",
);
const completed = computed(() =>
  (current.value?.runs ?? []).filter(
    (r) => !["QUEUED", "RUNNING"].includes(r.status),
  ),
);
const passed = computed(() =>
  completed.value.filter((r) => r.status === "PASSED"),
);
const label = (s: string) =>
  ({
    QUEUED: "排队中",
    RUNNING: "运行中",
    PASSED: "浏览器验收通过",
    STATIC_VALIDATED: "结构检查通过 · 浏览器未验收",
    FAILED: "未通过",
    BUDGET_EXCEEDED: "预算不足",
    INTERRUPTED: "运行中断",
  })[s] ?? s;
async function api(path: string, method = "GET", body?: unknown) {
  const response = await fetch("/api/workbench" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "workbench",
      ...(access.value ? { "X-Live-Access": access.value } : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.message ?? `请求失败 (${response.status})`);
  }
  return response.headers.get("content-type")?.includes("application/json")
    ? response.json()
    : response.text();
}
async function action(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
async function refresh() {
  if (current.value) {
    const id = current.value.id;
    const next = await api(`/projects/${id}`);
    if (current.value?.id === id) current.value = next;
  }
}
async function create() {
  await action(async () => {
    current.value = await api("/projects", "POST", {
      name: name.value || "我的 AI 项目",
    });
    projects.value = await api("/projects");
    name.value = "";
    selectedRun.value = "";
    answer.value = "";
    report.value = "";
  });
}
async function choose(id: string) {
  await action(async () => {
    current.value = await api(`/projects/${id}`);
    selectedRun.value = "";
    answer.value = "";
    sources.value = [];
    report.value = "";
  });
}
async function generate() {
  await action(async () => {
    if (!current.value) return;
    const r = await api(`/projects/${current.value.id}/runs`, "POST", {
      prompt: prompt.value,
      maxRepairs: maxRepairs.value,
      tokenBudget: 24000,
      requiredTexts: required.value.split("\n").filter(Boolean),
      checkInteraction: interaction.value,
      memoryStrategy: strategy.value,
      demoFailure: injectFailure.value,
    });
    selectedRun.value = r.id;
    await refresh();
  });
}
async function saveMemory() {
  await action(async () => {
    if (current.value) {
      current.value = await api(
        `/projects/${current.value.id}/memories`,
        "POST",
        { kind: kind.value, key: key.value, value: value.value },
      );
      value.value = "";
    }
  });
}
async function forget(id: string) {
  await action(async () => {
    if (current.value)
      current.value = await api(
        `/projects/${current.value.id}/memories/${id}`,
        "DELETE",
      );
  });
}
async function saveDocument() {
  await action(async () => {
    if (current.value) {
      current.value = await api(
        `/projects/${current.value.id}/documents`,
        "POST",
        { title: docTitle.value, content: docContent.value },
      );
      docContent.value = "";
    }
  });
}
async function readFile(event: Event) {
  const f = (event.target as HTMLInputElement).files?.[0];
  if (!f) return;
  if (f.size > 90000) {
    error.value = "请上传 90 KB 以内的文本文件";
    return;
  }
  docTitle.value = f.name;
  docContent.value = await f.text();
}
async function search() {
  await action(async () => {
    if (current.value) {
      const r = await api(
        `/projects/${current.value.id}/knowledge?q=${encodeURIComponent(query.value)}`,
      );
      answer.value = r.answer;
      sources.value = r.sources;
    }
  });
}
async function makeReport() {
  await action(async () => {
    if (current.value)
      report.value = await api(`/projects/${current.value.id}/report`);
  });
}
async function rollback() {
  await action(async () => {
    if (current.value && activeRun.value)
      current.value = await api(
        `/projects/${current.value.id}/select/${activeRun.value.id}`,
        "POST",
        {},
      );
  });
}
function download(content: string, filename: string, type = "text/plain") {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
let timer: ReturnType<typeof setInterval>;
onMounted(async () => {
  await action(async () => {
    config.value = await api("/config");
    projects.value = await api("/projects");
    current.value = projects.value[0] ?? null;
  });
  timer = setInterval(() => {
    if (running.value)
      refresh().catch((e) => {
        error.value = e.message;
      });
  }, 1500);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <a class="brand" href="/" aria-label="Agent Workbench 首页"
        ><span class="brand-icon">a<span>·</span></span>
        <div>Agent<br /><strong>Workbench</strong></div></a
      >
      <p class="nav-caption">个人 AI 工作台</p>
      <nav aria-label="产品导航">
        <button
          v-for="item in tabs"
          :key="item.id"
          :class="{ active: tab === item.id }"
          @click="tab = item.id"
        >
          <span>{{ item.icon }}</span
          >{{ item.label }}<b v-if="tab === item.id">↗</b>
        </button>
      </nav>
      <div class="project-picker">
        <label for="project">当前项目</label
        ><select
          id="project"
          :value="current?.id ?? ''"
          @change="choose(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>选择一个项目</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">
            {{ p.name }}
          </option></select
        ><input
          v-model="name"
          maxlength="80"
          placeholder="新项目名称"
          aria-label="新项目名称"
        /><button class="secondary full" :disabled="busy" @click="create">
          ＋ 新建项目
        </button>
      </div>
      <div class="sidebar-bottom">
        <span class="status-dot"></span
        >{{ config?.mode === "live" ? "真实模型模式" : "演示模式 · 无需密钥" }}
        <p>研究想法，成为可验证的作品。</p>
        <a
          href="https://github.com/BStronger1/agent-workbench"
          target="_blank"
          rel="noreferrer"
          >GitHub ↗</a
        >
      </div>
    </aside>
    <main>
      <header>
        <div class="breadcrumb">
          WORKSPACE <span>/</span> {{ tabs.find((t) => t.id === tab)?.label }}
        </div>
        <span class="mode-tag"
          >{{ config?.mode === "live" ? "LIVE" : "DEMO" }}<i></i
        ></span>
      </header>
      <section class="intro">
        <div>
          <p class="eyebrow">BUILD WITH CONTEXT. SHIP WITH EVIDENCE.</p>
          <h1>
            {{
              tab === "studio"
                ? "让想法，成为可用的作品。"
                : tab === "knowledge"
                  ? "让每次回答，都有据可循。"
                  : tab === "report"
                    ? "把开发过程，整理成成果。"
                    : "看见每一次运行的表现。"
            }}
          </h1>
          <p class="intro-text">
            {{
              tab === "studio"
                ? "从需求出发，带着项目记忆生成、检查和修复。"
                : tab === "knowledge"
                  ? "把项目文档、约束与决策放在一起，检索可以追溯的原文。"
                  : tab === "report"
                    ? "从同一个项目的资料和运行证据，生成可下载的开发汇报。"
                    : "保留成功与失败，分别查看演示运行和真实模型结果。"
            }}
          </p>
        </div>
        <span class="edition">PERSONAL LAB<br /><b>01 / WORKBENCH</b></span>
      </section>
      <div v-if="error" class="error" role="alert">
        {{ error }} <button @click="error = ''">关闭</button>
      </div>
      <div class="notice">
        <span>ⓘ</span>
        <p>
          {{
            config?.mode === "live"
              ? "真实调用会使用服务器配置的 API。请设置验收要求，并留意预算和运行状态。"
              : "当前为固定模板演示：可体验项目记忆、真实浏览器验收与修复流程，不代表模型生成能力。"
          }}<small v-if="config && !config.browserValidation"
            >浏览器验收尚未配置，结果只标记为“结构检查通过”。</small
          >
        </p>
      </div>
      <section v-if="!current" class="empty panel">
        <span class="empty-icon">◈</span>
        <h2>从你的第一个项目开始</h2>
        <p>一份项目空间，连接应用、知识和汇报。</p>
        <button class="primary" :disabled="busy" @click="create">
          创建我的项目 →
        </button>
      </section>
      <template v-else>
        <div class="project-heading">
          <h2>{{ current.name }}</h2>
          <span
            >{{ activeMemories.length }} 条有效记忆 ·
            {{ current.documents.length }} 份资料</span
          >
        </div>
        <div v-if="tab === 'studio'" class="studio-grid">
          <section class="panel composer">
            <div class="panel-title">
              <h3>01 <span>描述你的应用</span></h3>
              <span>HTML · 自包含应用</span>
            </div>
            <label for="prompt">这次想做什么？</label
            ><textarea
              id="prompt"
              v-model="prompt"
              rows="4"
              maxlength="2000"
              placeholder="例如：制作一个研究项目进度看板"
            ></textarea
            ><label for="required"
              >验收文本 <small>每行一项，必须出现在页面中</small></label
            ><textarea
              id="required"
              v-model="required"
              rows="2"
              maxlength="808"
            ></textarea>
            <div class="form-row">
              <label
                >记忆策略<select v-model="strategy">
                  <option value="retrieval">项目记忆检索</option>
                  <option value="window">最近 3 次需求</option>
                  <option value="none">不使用记忆</option>
                </select></label
              ><label
                >最多修复<select v-model="maxRepairs">
                  <option :value="0">0 次</option>
                  <option :value="1">1 次</option>
                  <option :value="2">2 次</option>
                  <option :value="3">3 次</option>
                </select></label
              >
            </div>
            <label class="check"
              ><input
                type="checkbox"
                v-model="interaction"
              />检查按钮点击后结果是否变化</label
            ><label v-if="config?.mode === 'demo'" class="check"
              ><input
                type="checkbox"
                v-model="injectFailure"
              />演示一次交互失败，再自动修复</label
            ><label v-if="config?.liveAccessRequired"
              >工作台访问口令<input
                v-model="access"
                type="password"
                autocomplete="off"
                placeholder="由部署者提供，仅保存在当前页面" /></label
            ><button
              class="primary full"
              :disabled="busy || running"
              @click="generate"
            >
              {{ running ? "正在生成与验证…" : "开始生成与验证" }}
              <span>↗</span>
            </button>
            <div class="memory-box">
              <h4>
                项目记忆 <span>{{ activeMemories.length }}</span>
              </h4>
              <div v-for="m in activeMemories" :key="m.id" class="memory">
                <div>
                  <strong>{{ m.key }}</strong>
                  <p>{{ m.value }}</p>
                </div>
                <button @click="forget(m.id)" aria-label="停用记忆">×</button>
              </div>
              <details>
                <summary>＋ 添加或更新记忆</summary>
                <select v-model="kind" aria-label="记忆类型">
                  <option value="constraint">约束</option>
                  <option value="decision">决策</option>
                  <option value="lesson">经验</option></select
                ><input
                  v-model="key"
                  placeholder="记忆名称"
                  maxlength="80"
                  aria-label="记忆名称"
                /><textarea
                  v-model="value"
                  rows="2"
                  placeholder="记住哪些要求？同名记忆会替换旧版本"
                  maxlength="1500"
                  aria-label="记忆内容"
                ></textarea
                ><button class="secondary" :disabled="busy" @click="saveMemory">
                  保存记忆
                </button>
              </details>
            </div>
          </section>
          <section class="panel preview">
            <div class="panel-title">
              <h3>02 <span>预览与运行证据</span></h3>
              <div class="segmented">
                <button
                  :class="{ selected: previewTab === 'preview' }"
                  @click="previewTab = 'preview'"
                >
                  预览</button
                ><button
                  :class="{ selected: previewTab === 'trace' }"
                  @click="previewTab = 'trace'"
                >
                  过程</button
                ><button
                  :class="{ selected: previewTab === 'code' }"
                  @click="previewTab = 'code'"
                >
                  代码
                </button>
              </div>
            </div>
            <div v-if="activeRun" class="run-toolbar">
              <span
                class="pill"
                :class="{ success: activeRun.status === 'PASSED' }"
                >{{ label(activeRun.status) }}</span
              ><small
                >{{ activeRun.attempts.length }} 次尝试 ·
                {{ (activeRun.durationMs / 1000).toFixed(1) }}s</small
              >
            </div>
            <iframe
              v-if="previewTab === 'preview' && artifactUrl"
              :key="artifactUrl + activeRun?.status"
              :src="artifactUrl"
              sandbox="allow-scripts"
              title="生成的应用预览"
              referrerpolicy="no-referrer"
            ></iframe>
            <div v-else-if="previewTab === 'trace' && activeRun" class="trace">
              <ol>
                <li v-for="(event, i) in activeRun.events" :key="i">
                  <small
                    >{{ new Date(event.at).toLocaleTimeString() }} ·
                    {{ event.stage }}</small
                  >
                  <p>{{ event.message }}</p>
                </li>
              </ol>
              <section
                v-for="a in activeRun.attempts"
                :key="a.number"
                class="attempt"
              >
                <strong>尝试 {{ a.number + 1 }} · {{ a.browserStatus }}</strong>
                <p v-for="e in a.errors" :key="e" class="failure-text">
                  {{ e }}
                </p>
                <img
                  v-if="a.screenshot"
                  :src="`/api/workbench/projects/${current.id}/runs/${activeRun.id}/screenshot/${a.number}`"
                  :alt="`第 ${a.number + 1} 次浏览器验收截图`"
                />
              </section>
              <p v-if="activeRun.error" class="failure-text">
                {{ activeRun.error }}
              </p>
              <details>
                <summary>本次使用的记忆来源</summary>
                <p v-for="s in activeRun.memorySources" :key="s.id">
                  {{ s.title }}：{{ s.excerpt
                  }}<small class="source-id">{{ s.id }}</small>
                </p>
              </details>
            </div>
            <pre
              v-else-if="previewTab === 'code' && activeRun?.attempts.length"
              class="code"
              >{{ activeRun.attempts.at(-1)?.html }}</pre
            >
            <div v-else class="preview-empty">
              <div class="wireframe">
                <div></div>
                <i></i><i></i><span></span><span></span><span></span>
              </div>
              <h3>
                {{
                  running ? "作品正在生成与检查" : "你的下一个作品，从这里开始"
                }}
              </h3>
              <p>填写需求并运行，查看页面和验证过程。</p>
            </div>
            <div v-if="activeRun?.attempts.length" class="preview-footer">
              <span>预览在隔离页面中运行</span
              ><button
                class="text-button"
                @click="
                  download(
                    activeRun.attempts.at(-1)!.html,
                    'index.html',
                    'text/html',
                  )
                "
              >
                下载 HTML ↓
              </button>
            </div>
          </section>
        </div>
        <div v-if="tab === 'knowledge'" class="two-columns">
          <section class="panel padded">
            <h3>添加项目资料</h3>
            <p class="muted">
              支持粘贴文本或导入 .txt / .md，资料只属于当前浏览器的项目空间。
            </p>
            <input
              v-model="docTitle"
              maxlength="100"
              aria-label="文档标题"
              placeholder="文档标题"
            /><textarea
              v-model="docContent"
              rows="10"
              maxlength="30000"
              aria-label="文档内容"
              placeholder="粘贴需求文档、研究笔记或项目说明…"
            ></textarea
            ><input
              ref="documentFile"
              type="file"
              accept=".md,.txt"
              @change="readFile"
            /><button class="primary" :disabled="busy" @click="saveDocument">
              保存资料
            </button>
            <p v-for="d in current.documents" :key="d.id" class="document-item">
              ▤ {{ d.title }} <small>{{ d.content.length }} 字符</small>
            </p>
          </section>
          <section class="panel padded">
            <h3>检索项目知识</h3>
            <p class="muted">
              基于关键词与中文双字匹配，返回带段落来源的原文。
            </p>
            <input
              v-model="query"
              maxlength="1000"
              aria-label="检索问题"
              placeholder="例如：项目的目标用户是谁？"
              @keyup.enter="search"
            /><button class="primary" :disabled="busy" @click="search">
              查找依据 ↗
            </button>
            <p v-if="answer && !sources.length">{{ answer }}</p>
            <article v-for="s in sources" :key="s.id" class="source-card">
              <strong>{{ s.title }}</strong>
              <p>{{ s.excerpt }}</p>
              <small>{{ s.id }}</small>
            </article>
          </section>
        </div>
        <section v-if="tab === 'report'" class="panel padded">
          <div class="panel-title">
            <div>
              <h3>项目开发汇报</h3>
              <p class="muted">
                确定性整理已有记录，包含来源、验收状态、尝试次数和汇报提纲。
              </p>
            </div>
            <button class="primary" :disabled="busy" @click="makeReport">
              生成汇报
            </button>
          </div>
          <pre v-if="report" class="report">{{ report }}</pre>
          <div v-else class="empty">
            <h3>让过程也成为你的成果</h3>
            <p>先添加项目资料或运行一次应用，再生成汇报。</p>
          </div>
          <button
            v-if="report"
            class="secondary"
            @click="download(report, 'project-report.md', 'text/markdown')"
          >
            下载 Markdown ↓
          </button>
        </section>
        <section v-if="tab === 'metrics'">
          <div class="stat-grid">
            <div class="panel stat">
              <small>已结束运行</small><b>{{ completed.length }}</b
              ><span>当前项目</span>
            </div>
            <div class="panel stat">
              <small>浏览器验收通过</small
              ><b>{{
                completed.length
                  ? ((passed.length / completed.length) * 100).toFixed(0) + "%"
                  : "—"
              }}</b
              ><span
                >{{ passed.length }} / {{ completed.length }} 次 ·
                含失败与中断</span
              >
            </div>
            <div class="panel stat">
              <small>真实模型运行</small
              ><b>{{ completed.filter((r) => r.mode === "live").length }}</b
              ><span>演示数据不计入模型效果</span>
            </div>
          </div>
          <div class="panel padded table-wrap">
            <div class="panel-title">
              <h3>版本与运行记录</h3>
              <button
                class="secondary"
                @click="
                  download(
                    JSON.stringify(current.runs, null, 2),
                    'runs.json',
                    'application/json',
                  )
                "
              >
                导出 JSON
              </button>
            </div>
            <table>
              <thead>
                <tr>
                  <th>需求 / 模式</th>
                  <th>状态</th>
                  <th>尝试</th>
                  <th>耗时</th>
                  <th>Token / 估算费用</th>
                  <th>版本</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in [...current.runs].reverse()" :key="r.id">
                  <td>
                    {{ r.prompt.slice(0, 40)
                    }}<small>{{ r.mode }} · {{ r.model }}</small>
                  </td>
                  <td>{{ label(r.status) }}</td>
                  <td>{{ r.attempts.length }}</td>
                  <td>{{ (r.durationMs / 1000).toFixed(1) }}s</td>
                  <td>
                    {{
                      r.usageKnown ? r.inputTokens + r.outputTokens : "未知"
                    }}
                    /
                    {{
                      r.estimatedCost == null
                        ? "未配置价格"
                        : r.estimatedCost.toFixed(5)
                    }}
                  </td>
                  <td>
                    <button
                      class="text-button"
                      @click="
                        selectedRun = r.id;
                        tab = 'studio';
                      "
                    >
                      查看</button
                    ><span v-if="r.id === current.selectedRunId">
                      · 当前成果</span
                    ><button
                      v-else-if="
                        ['PASSED', 'STATIC_VALIDATED'].includes(r.status)
                      "
                      class="text-button"
                      @click="
                        selectedRun = r.id;
                        rollback();
                      "
                    >
                      设为成果
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <p v-if="!current.runs.length" class="muted">还没有运行记录。</p>
          </div>
          <p class="muted">
            这里是工作流观测数据。跨模型效果比较请使用仓库中的固定评测集，报告中需注明演示或真实调用。
          </p>
        </section>
      </template>
      <footer>
        <span>Agent Workbench <b>·</b> BStronger1</span
        ><span>项目记忆 / 可验证生成 / 来源可追溯</span>
      </footer>
    </main>
  </div>
</template>
