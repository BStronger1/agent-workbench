# 简历项目条目

## 中文

**Agent Workbench｜项目记忆驱动的 AI 应用生成与自动验收工作台**

Java 21 · Spring Boot · Vue 3 · TypeScript · Playwright

- 实现大模型应用生成工作流，将需求、项目记忆和验收要求组装为模型上下文，通过 Playwright 检查生成页面，将失败原因与上一版代码回传模型，支持最多 3 次修复及版本回退。
- 实现项目约束、决策与经验的版本化管理，采用中文双字和关键词检索上下文，支持无记忆、近期需求、检索记忆三种策略及来源追溯。
- 实现用户自选模型与 AES-256-GCM 加密的 API Key 配置，为任务加入有限队列、Token 预算检查及供应商用量记录；完成 25 项后端测试、浏览器端到端验证和 36 项确定性演示验收，部署 Linux 内网 HTTPS 服务。

当前边界：真实模型适配器已实现但尚未配置密钥实测；36 项演示结果属于工作流功能验证，不能写成真实模型效果提升。最新测试结果见 EVALUATION.md。

## English

**Agent Workbench — Personal AI workspace with project memory and browser-validated repair**

- Implemented an LLM app-generation workflow with retrieved project context, Playwright acceptance checks and failure feedback into up to three model repair attempts with version rollback.
- Built versioned constraints, decisions and lessons with Chinese-bigram/keyword retrieval, source references and no-memory/recent-request/retrieved-memory strategies.
- Added user-configured models, AES-256-GCM encrypted keys, bounded queues and token-budget checks; verified 25 backend tests, browser checks and 36 deterministic demo cases with private Linux HTTPS deployment. Actual model quality remains unverified until real API testing.
