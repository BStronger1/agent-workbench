# AI 技术栈项目简历

以下描述区分已实现能力与验证范围；未进行模型微调。

### Agent Workbench — 基于 LangGraph 与 RAG 的 AI 应用开发工作台
**个人项目 · 2026 年 10 月**

[源代码](https://github.com/BStronger1/agent-workbench) · [项目概览](https://bstronger1.github.io/zh/projects/agent-workbench/)

Python / FastAPI · LangChain · LangGraph · PostgreSQL / pgvector · Embedding / RAG · Playwright · Java / Spring Boot · Vue / TypeScript

* 基于 LangChain 与 LangGraph 构建需求规划、代码生成、浏览器验收、独立评审及有界修复工作流；支持单角色与多角色模式、计划人工确认和持久化检查点恢复，通过调用账本复用已完成结果，阻止不确定请求自动重放。
* 实现 RAG 知识模块：使用本地多语言 Embedding 与 pgvector 存储项目文档和有效记忆，融合中文双字/关键词检索与向量召回，通过 RRF 排序、空间/项目过滤和来源 ID 校验提供带引用回答。
* 将 Playwright 验收升级为勾选、输入、点击及结果断言的结构化契约，在生成前固定验收标准，将执行错误与评审意见回传编码角色，保存失败产物、截图和修复记录。
* 支持用户自选模型及 AES-256-GCM 加密密钥配置，使用有限任务队列、调用前 Token 预算检查及分角色调用用量记录；保留 Java 基础流程与演示兼容性。
* 完成后端、状态图恢复、真实 pgvector/Embedding 和浏览器集成验证；基础链路使用 DMXAPI-deepseek-v4-flash 完成 6 项真实任务（8 次调用，4 项通过），保留全部失败证据。

新增图编排版的外部模型对照和内网部署更新受网络连接影响待完成；未进行模型微调。


[升级架构与验证状态](AI-UPGRADE.md)
