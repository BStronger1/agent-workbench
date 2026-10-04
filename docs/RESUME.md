# 简历项目条目

## 中文

**Agent Workbench｜带项目记忆与自动验收的个人 AI 工作台**

Java 21 · Spring Boot · Vue 3 · TypeScript · Playwright

- 开发个人 AI 工作台，打通需求输入、自包含 HTML 生成、浏览器验收、有界修复、版本选择与源码导出。
- 实现项目约束、决策和经验的版本管理及词法检索，支持旧记忆失效、来源追溯，以及无记忆、近期需求、检索记忆三种上下文策略。
- 实现项目资料检索、开发汇报和运行记录面板；支持用户自填模型接口和 Key，配置按空间隔离并加密存储，支持连接测试和动态切换。

当前边界：真实模型适配器已实现但尚未配置密钥实测；36 项演示结果属于工作流功能验证，不能写成真实模型效果提升。最新测试结果见 EVALUATION.md。

## English

**Agent Workbench — Personal AI workspace with project memory and browser-validated repair**

- Developed a Java/Spring Boot and Vue AI workbench connecting self-contained HTML generation, bounded repair, browser interaction checks, version selection and artifact export.
- Implemented versioned project constraints, decisions and lessons with lexical retrieval, source references and no-memory/recent-request/retrieval context modes.
- Added source-grounded document retrieval, Markdown reporting and run evidence; enabled user-configured models and API keys with owner-scoped encrypted storage, connection testing and runtime switching. Live provider compatibility and generation quality remain unverified until real API testing.
