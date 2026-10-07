# LangGraph 与 RAG 真实模型验证

**后续修复：** 原失败清单场景已完成控件唯一性与类型修复，同模型、同契约定向复测单角色和多角色均通过（2/2）。此次在本地完整链路验证，turing 同步待 SSH 恢复；不合并为新的六任务成功率。见 [清单修复报告](CHECKLIST-REGRESSION.md)。

测试日期：2026-10-08（Asia/Singapore）。运行于实际 Linux HTTPS 部署，模型标识为 `DMXAPI-deepseek-v4-flash`。

## 方法与范围

固定三类自编开发任务：点击计数、勾选后更新清单、输入后提交阅读任务。每类分别运行单编码角色和规划/编码/评审三角色，冻结相同验收契约，不使用检索上下文，最多一次修复、每任务 50000 Token 保守预算。G-01 协作模式实际经过计划暂停和显式恢复。

规划、评审与 RAG 使用 JSON/Pydantic 校验；编码输出完整 HTML，再经过结构检查及带 CSP 的隔离 Chromium 验收。验收步骤和所需文本不会因修复而改变。

这是一次开发场景运行，不是独立保留测试集、随机重复实验或通用模型能力基准。不得据此声称多 Agent 优于单 Agent。

## 配对任务结果

| 场景 | 模式 | 首轮 | 最终 | 调用 | 输入 / 输出 Token | 耗时（秒） |
|---|---|---|---|---:|---:|---:|
| G-01 | graph_single | 通过 | PASSED | 1 | 270 / 1260 | 48.37 |
| G-01 | graph_multi | 通过 | PASSED | 3 | 3278 / 2251 | 86.28 |
| G-02 | graph_single | 失败 | FAILED | 2 | 1635 / 1986 | 75.27 |
| G-02 | graph_multi | 失败 | FAILED | 5 | 5975 / 3093 | 123.64 |
| G-03 | graph_single | 通过 | PASSED | 1 | 326 / 2098 | 78.74 |
| G-03 | graph_multi | 通过 | PASSED | 3 | 2416 / 1791 | 69.45 |

新版已部署内网 HTTPS；使用 DMXAPI-deepseek-v4-flash 完成 6 项同契约单角色/多角色真实任务（15 次调用，4/6 验收通过）及 2/2 项带引用 RAG 验证。失败记录完整保留，结果仅适用于这些开发场景。

- graph_single：2/3 通过，4 次调用，平均任务耗时 67.46 秒。
- graph_multi：2/3 通过，11 次调用，平均任务耗时 93.12 秒。

失败详情（保留初次与修复后记录）：

- G-02 / graph_single：第 1 次：Missing required text: 项目进度；第 2 次：结构化交互步骤或断言失败。
- G-02 / graph_multi：第 1 次：结构化交互步骤或断言失败；第 2 次：结构化交互步骤或断言失败。

离线检查发现，两种模式的清单产物均将 `selection-item` 复用于四个复选框，违反 Playwright 单目标定位要求；单角色首轮还缺少必需文字“项目进度”。评审意见和一次修复未消除重复定位问题，原失败结果保留。不能把角色分工已运行等同于质量提升。原 Java 基础链路的 4/6 结果使用不同交互契约，不能与本表作效果提升对比。

## RAG 验证

使用自编项目文档，经本地多语言 ONNX Embedding、pgvector 与 RRF 检索后调用真实模型回答。检查答案包含期望事实，且非空引用全部属于实际召回集合：

- 本项目开发费用上限是多少？：通过；期望事实 `500`。
- API密钥需要用什么算法加密保存？：通过；期望事实 `AES-256-GCM`。

引用 ID 合法不等于通用答案忠实性。两个开发探针不能替代独立 RAG 质量评测。

## 调试记录与用量

最终图工作流 15 次调用、26379 Token；RAG 2 次调用、569 Token。此前两次调试执行共 6 次已完成调用、7518 Token，均计入记录，没有删除。以上恢复联网后的已知合计为 23 次调用、34466 Token；价格未配置，不推算金额。

两次调试中的单角色任务通过；多角色编码分别因 JSON 字符串内的未转义换行、未转义 HTML 引号而中断。随后加入缓存回复兼容，并将编码角色改为完整 HTML 文本输出；没有通过猜测补全 JSON 引号来放宽验收。另修复文本变化断言的空白误判，并用无操作按钮回归覆盖。

更早的网络失败请求用量未知，仍单独保留，不能视为零费用。最终运行与调试运行分开报告，结果不是挑选最好的一次。

## 工程与部署

17 项 Python 测试在部署环境通过，包含实际 PostgreSQL/pgvector、真实本地 Embedding、检查点、调用缓存、预算和输出解析。5 项 Node 控制/契约测试通过；HTTPS 浏览器冒烟与个人模型配置回归通过。Java 回归为 29 项。

部署包括 Spring Boot、仅回环监听的 FastAPI、用户目录中的 PostgreSQL 17.11 / pgvector 0.8.2。向量模型离线缓存，AI 与数据库使用内部凭据；真实测试的临时个人 API 配置在结束后删除。未进行模型微调。

## 原始证据

- [最终图任务](../evidence/graph-live.json) · [RAG](../evidence/rag-live.json)
- [换行中断](../evidence/graph-live-initial.json) · [引号中断](../evidence/graph-live-json-quote-failure.json)
- [早期网络中断](../evidence/graph-live-network-failure.json)
- [离线产物复验](../evidence/graph-artifact-replay.json) · [HTML 与截图](../evidence/graph-artifacts)
- [部署浏览器检查](../evidence/deployed-smoke.json) · [模型配置检查](../evidence/deployed-provider-smoke.json)
