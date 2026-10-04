# Agent Workbench

个人 AI 工作台：把项目记忆、应用生成、浏览器验收与开发汇报连接起来。

**状态：可运行的无密钥演示版；真实模型接口已实现，尚未使用真实 API 验证。** 演示生成采用固定模板，浏览器验收、状态持久化、记忆检索和资料检索实际执行。演示成功率不是模型效果指标。

![工作台界面](docs/images/desktop.png)

## 产品

| 入口 | 当前能力 |
|---|---|
| 应用工坊 | 自包含 HTML 应用；需求与文本/按钮验收契约；生成→检查→有界修复；尝试记录、截图、版本选择和源码下载 |
| 项目知识 | 文本/Markdown 资料导入；中文双字和关键词检索；段落来源；无匹配时明确提示 |
| 汇报助手 | 从同一项目的有效记忆、资料、运行证据确定性生成 Markdown 汇报和演示提纲 |
| 运行评测 | 查看耗时、尝试次数、模型模式、Token 和配置价格下的估算费用；导出 JSON；固定评测集 |

项目记忆包含约束、决策和经验。同名更新会使旧记忆失效，旧版本仍可审计；支持停用。生成时可选择无记忆、最近三次需求或项目记忆检索。当前为词法检索，尚未实现向量检索、HMMEM 或自动提炼记忆。

## 本地运行

需要 Java 21+、Maven 3.9+、Node 22。无需 MySQL、Redis、云存储或模型密钥。

```bash
npm ci --prefix web
npm run build --prefix web
mkdir -p src/main/resources/static
cp -R web/dist/. src/main/resources/static/
mvn -gs settings.xml -s settings.xml package
java -jar target/agent-workbench-0.1.0.jar
```

打开 `http://127.0.0.1:8123`。未配置浏览器时，结果只标为 `STATIC_VALIDATED`，不会标为浏览器验收通过。

启用真实浏览器验收：

```bash
cd qa
npm ci
npx playwright install chromium
cd ..
export QA_COMMAND="[\"node\",\"$(pwd)/qa/worker.mjs\"]"
java -jar target/agent-workbench-0.1.0.jar
```

Linux 的浏览器沙箱需要可用的用户命名空间及 Chromium 运行库。不能启动时任务标为失败，不通过关闭沙箱来掩盖环境问题。

首次进入点击“创建我的项目”；添加一条约束；勾选“演示一次交互失败，再自动修复”；运行后在“过程”中查看失败截图与第二次验收。演示会确定性修复预设缺陷，**没有模拟真实模型推理质量**。

## 后续接入 API

复制 `.env.example` 为服务器上的 `.env`，填写 `LLM_API_KEY`、HTTPS `LLM_BASE_URL`、`LLM_MODEL`、至少 24 字符的 `LIVE_ACCESS_TOKEN`，将 `WORKBENCH_MODE` 改为 `live`，再重启。启动脚本会加载 `.env`；直接 `java -jar` 时需要自行导出环境变量。

浏览器只输入工作台访问口令，模型密钥留在服务器。当前实现 OpenAI-compatible Chat Completions HTTP 接口，要求模型返回 `{"html":"..."}`。每次最多输出 4096 tokens；任务可设 0–3 次修复和保守 Token 预算。未返回用量的供应商不推算消耗；未配置价格不估算费用。真实供应商的兼容性、质量与账单仍需配置后验证。

## 验证

```bash
mvn -gs settings.xml -s settings.xml test
cd qa
node smoke.mjs
node evaluate.mjs
# 真实 API 评测需显式 --live，并会产生费用：
# LIVE_ACCESS_TOKEN=... node evaluate.mjs --live
```

见 [验证记录](docs/EVALUATION.md)、[演示评测原始数据](evidence/evaluation-demo.json) 和 [架构与边界](docs/ARCHITECTURE.md)。CI 会构建前后端、运行单元测试和浏览器端到端测试。

## 部署

前端静态资源打包进 Spring Boot JAR，可在单台服务器的用户目录运行。部署脚本、独立运行环境目录与操作步骤见 [部署说明](docs/DEPLOYMENT.md)。当前针对个人工作台，没有微服务、容器编排或多实例数据库要求。

## 项目来源与贡献范围

这个项目由对 [yu-ai-code-mother](https://github.com/liyupi/yu-ai-code-mother) 的学习和改造需求发展而来。公开仓库是新写的独立工作台模块，不包含原仓库 Java/Vue 源码、课程材料、品牌资源或 Git 历史；原项目保留在本地作为参考。未将上游实现宣称为个人原创。

新增实现：独立无密钥运行链路、项目记忆版本管理、带验收契约的有界修复、浏览器交互验证、同源隔离预览、来源检索、证据汇报、评测集与部署材料。开发使用 AI 辅助，简历与报告按实际测试结果描述。MIT 许可仅适用于本仓库新增代码，详见 [NOTICE](NOTICE.md)。
