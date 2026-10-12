# AI 技术栈项目简历

### Agent Workbench — Agent Harness、Skills 与 RAG 应用开发工作台
**个人项目 · 2026 年 10 月**

[源代码](https://github.com/BStronger1/agent-workbench) · [项目概览](https://bstronger1.github.io/zh/projects/agent-workbench/)

LangChain · LangGraph · Agent Skills · PostgreSQL / pgvector · Embedding / RAG · Playwright · Python / FastAPI · Spring Boot · Vue / TypeScript

* 基于 LangChain/LangGraph 构建规划、编码、验收、评审与有界修复流程，结合 SQLite 检查点、调用账本、人工确认和 Token 预算实现任务执行 Harness，复用已完成响应并阻止不确定付费请求自动重放。
* 设计页面交互修复 Skill，实现按错误类型路由、按需注入参考资料和技能版本固定；接入结构化局部补丁工具，校验唯一锚点与非重叠修改，保留原 HTML、补丁及验收轨迹。
* 使用本地 384 维多语言 Embedding 与 pgvector 构建 RAG，融合中文关键词与向量召回，通过 RRF 排序、空间/项目隔离及来源 ID 校验提供带引用回答。
* 完成 48 次真实模型调用的开发评测。在 8 个固定场景、每方案 16 次修复的 Skill 迭代中，总 Token 从 47,346 降至 31,814（减少 32.8%），总体通过率同为 81.25%；保留全部失败和关闭技能的对照。
* 部署内网 HTTPS，支持用户自选模型及 AES-256-GCM 加密密钥；通过 31 项 Java、48 项 Python 测试及浏览器验证，覆盖真实 pgvector/Embedding、技能路由、补丁边界与状态恢复。

关闭 Skill 的基线通过率为 87.5%，因此技能默认关闭、可选启用。以上是开发场景的非同期对照，未证明质量提升或泛化效果；未进行模型微调。[Skill 评测与取舍](https://github.com/BStronger1/agent-workbench/blob/main/docs/SKILL-EVALUATION.md) · [工作流与 RAG 验证](https://github.com/BStronger1/agent-workbench/blob/main/docs/GRAPH-LIVE-RESULTS.md)
