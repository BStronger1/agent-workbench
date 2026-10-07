# AI 工作流升级

## 已实现的运行结构

Vue → Spring Boot（归属校验、模型配置、有限队列）→ 本机 FastAPI → LangGraph 状态图。

- LangChain ChatOpenAI：兼容接口调用，JSON/Pydantic 输出校验，SDK 自动重试关闭。
- LangGraph：规划、可选人工确认、编码、浏览器验收、独立评审、有界修复；SQLite 检查点支持单实例恢复。
- 单角色对照只调用编码模型；协作模式按规划、编码、评审分工，使用独立输入上下文。这是受控角色工作流，不包含任意工具自动执行或自主子任务扩张。
- Playwright：只允许 check/fill/click/assert_text/assert_changed，目标限定 data-testid；文本断言精确匹配，生成后的修复不能修改固定验收契约。
- RAG：LangChain 文本切分、FastEmbed 的 paraphrase-multilingual-MiniLM-L12-v2（384 维本地 ONNX）、PostgreSQL/pgvector 余弦检索、中文双字/关键词检索与 RRF 融合。返回来源 ID；模型回答仅接受召回集合中的引用 ID。

引用 ID 合法不等于语义完全受证据支持；仍需人工抽检答案忠实性。当前向量查询使用精确检索，未宣称 HNSW 性能或大规模召回效率。

## 恢复与费用边界

API Key 只保留在请求内存及原有加密配置中，不放入状态图、检查点或调用账本。关闭 LangSmith 自动追踪。Python 仅绑定 127.0.0.1，内部请求需要 32 字符以上口令；Spring Boot 校验用户空间。

每个模型调用在请求前写 pending，收到响应后保存结果及 usage。恢复时复用已完成调用；pending 的不确定请求不会自动重复。此机制防止盲目重试，不承诺供应商端 exactly-once。此类任务需要核查后新建。预算是保守预检查，不是服务商账单硬上限。

单实例 Python 使用 SQLite 检查点和调用账本；业务 JSON 快照也仍是单 JVM 写入。暂停确认后可恢复；网络中断后需要用户显式恢复，不在重启时自动发起付费请求。

## 本地与 Linux 部署

Python 3.12、Java 21+、Node 22、Chromium。安装 Python 依赖：

```bash
python3 -m venv runtime/ai-venv
runtime/ai-venv/bin/pip install -r ai_service/requirements.lock
```

为 PostgreSQL 单独创建应用数据库，安装 vector 扩展。可在支持 Docker 的环境使用：

```bash
# VECTOR_PASSWORD 由部署者设置；不要提交真实值
 docker compose -f deploy/compose.ai.yml up -d
```

在忽略提交的 `.env` 设置：

```text
AI_SERVICE_URL=http://127.0.0.1:18124
AI_SERVICE_TOKEN=<生成至少32字符的随机内部口令>
VECTOR_DSN=postgresql://workbench:<数据库密码>@127.0.0.1:15432/workbench
```

运行 `bash deploy/start-ai.sh`，再按原部署步骤启动 Java。首次混合检索下载约 220 MB 的本地向量模型，缓存位于 `runtime/embeddings`。仅启用图工作流时不需要数据库；选择混合检索而数据库不可用时明确失败，不静默退回关键词。

界面：保存个人模型 → 应用工坊选择单角色或规划/编码/评审协作 → 选择交互验收 → 可选“生成前确认计划”。项目知识可切换原文检索、混合检索或带引用的 AI 回答。

## 测试与真实评测

```bash
python -m pytest ai_service/tests -q
node --test qa/contract.test.mjs
# 真实调用需显式 --live 和临时模型环境配置，与 live-smoke 相同
node qa/graph-live.mjs --live
```

图评测固定三种交互场景，每场景对比单角色和三角色，均使用相同验收步骤、无检索、最多一次修复。最多 21 次调用、每任务预算 50000 Token。保留全部失败，不凭小样本宣称多 Agent 优于单 Agent。向量检索与生成对照分开测量。

## 微调准备

`python -m ai_service.training_export evidence/graph-live.json data/training-candidates.jsonl` 只导出真实验收通过的候选样本，按任务分组建议切分，防止同一任务的不同角色产物跨训练/验证集。所有样本仍标记待人工审校。

尚未进行 LoRA/QLoRA 训练，不宣称微调效果。进入训练前需积累足够多样且经审校的任务，独立保留测试集，并选择具备训练许可的开放权重模型及可用算力；已有聊天 API 不等于训练权限。
## 本次验证状态（2026-10-07）

- CI 提交 95d4601：基础工作台构建/回归成功；13 项 Python 测试成功，包含真实 pgvector 数据隔离、更新失效删除，以及真实 ONNX Embedding 与数据库联合检索。
- 六条中文检索开发样例：混合 Recall@3=5/6，词法 Recall@3=2/6；[原始结果](../evidence/retrieval-fixtures.json)。未做独立测试集和重复实验。
- 新图流程的真实模型对照在首次请求因 HTTPS 连接异常中断，没有获得模型产物，剩余任务停止；[完整中断记录](../evidence/graph-live-network-failure.json)。请求用量未知，不能记为真实模型通过。
- 本地前后端、Java→Python 接入及浏览器回归完成。turing SSH 当前无法建立连接，新版本尚未部署到该服务器；旧服务部署记录不代表本次升级上线。
- 真实测试的临时个人模型配置已清除，公开文件不含密钥。

新增回归覆盖 Java 重启后恢复入口保留、训练候选样本分组与失败排除。本地最终测试为 29 项 Java 和 12 项 Python；两项需要真实数据库的 Python 测试由 CI 执行。默认 AI 服务允许域名保持原范围；未扩展到更多服务商。
