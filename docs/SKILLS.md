# Agent Skills 与任务执行 Harness

工作台内置 `web-ui-acceptance-repair`，在生成 HTML 的交互验收失败后，为编码和评审角色提供诊断流程与针对性的参考资料。首次生成沿用原有提示词，技能关闭时也沿用原有修复上下文。v1.1 的编码角色在修复时提交结构化局部替换，保留未修改的 HTML。用户在单角色或多角色流程中可切换“交互失败时使用修复技能”，在“过程”查看实际触发的名称和版本。

## 运行结构

```text
plan → approval → code → validate → select_skill → review → code / finish
                                单角色跳过 review
```

- **运行控制层（harness）**：LangGraph 决定下一步，SQLite 保存检查点，调用账本管理已完成结果与不确定请求，宿主实施 Token 预算、修复上限及固定验收契约。
- **技能注册**：服务只读取仓库 `skills/` 下受信任的 SKILL.md。校验名称、描述、版本和引用路径；文档不能注册任意命令或扩大工具权限。
- **选择策略**：按实际验收错误确定是否适用。定位/控件错误使用 `targets.md`，状态/结果/脚本错误使用 `state.md`，混合错误可以加载两份。已通过、无关错误、环境故障和修复次数耗尽均不注入技能上下文。
- **上下文组织**：注册时读取并校验资源用于版本指纹；模型只接收被选中的正文和相关参考资料，不接收整个技能目录。当前一个内置技能采用明确规则选择，无额外 LLM 路由调用。
- **版本与证据**：新运行固定技能清单及 SHA-256，换行统一为 LF。恢复时校验原版本；发生漂移则要求恢复原包或新建任务。保存技能版本、内容哈希、参考资料、上下文字符数、触发原因和契约哈希。
- **工具执行**：v1.1 使用 Pydantic 校验 old/new 替换列表，宿主要求锚点在原文中唯一且区间不重叠，按原始位置应用最多 6 处替换。拒绝不存在、重复、重叠、无变化或破坏完整 HTML 的补丁。原文不被猜测修正；保存每次 edits、前后哈希和 APPLIED/REJECTED。既有 Validator / Playwright 决定结果，Skill 不执行 shell、不修改验收、不决定 PASSED。图状态与报告不保存 API Key。

这是一项面向具体任务的 Agent Skill 集成；没有增加模型训练或任意第三方技能执行能力。已有规划、编码和评审角色仍由固定状态图编排。

## 文件

- [技能入口](../skills/web-ui-acceptance-repair/SKILL.md)
- [加载与路由](../ai_service/skills.py)
- [LangGraph 接入](../ai_service/graph.py)
- [受控补丁应用器](../ai_service/patching.py)
- [修复对照评测入口](../ai_service/skill_eval.py)
- [固定案例及契约](../qa/skill-cases/cases.json)

增加技能时，编写包和明确的适用条件，在注册器扩展路由与工具接口，并补充正例、非触发例及真实行为验证。用户文档和生成 HTML 始终是输入数据，不会成为受信任技能。

## 修复对照评测

8 个固定案例：2 个历史模型失败产物、6 个新增开发探针；覆盖目标重复、错误控件、数值状态、实时输入、重绘后事件绑定、事件冒泡、筛选后的状态统计及结果文本。用例在真实运行前固定，不根据评测结果修改。

```bash
# QA_COMMAND 指向已有 Node + qa/worker.mjs，Chromium 需已安装
python -m ai_service.skill_eval
# 仅检查原始产物确实失败，不调用模型
python -m ai_service.skill_eval --live --repeats 2
# 交互终端隐藏输入 API Key；也可从 stdin 接收 Credentials JSON
```

真实评测使用生产 LangGraph 与 Validator。适配器给两组注入相同的失败 HTML 作为 coder-0（不调用模型），coder-1 才是真实修复调用。开启与关闭 Skill 使用相同模型、temperature=0.2、每次最多一次修复和 50000 Token 保守预算；每个案例每组重复两次，交替执行组顺序，共最多 32 次调用。累计预算停止阈值 180000 Token，未知请求结果立即停止，不自动重放。

因此主要指标是**固定失败产物的一次修复通过率**，不等于从需求开始生成的端到端成功率。统计全部试验，包括失败和解析中断；报告成对胜负、供应商 Token 与运行耗时。报告已存在时拒绝覆盖，代码、技能、HTML 和契约的哈希在调用前写入报告。

初轮纯指导型 Skill v1.0 与关闭 Skill 的完整 32 次记录保存在 [首轮报告](../evidence/skill-ablation.json)：分别通过 13/16 和 14/16。未得到收益，且整页重写产生了额外脚本错误，因此新增 v1.1 局部替换工具并精简上下文。

v1.1 使用 \`--baseline-report evidence/skill-ablation.json --output evidence/skill-edits-evaluation.json\` 完整复用全部 16 条基线（包括两条失败），新增 16 次技能组调用。脚本验证案例、模型、温度、预算和重复次数一致；[离线等价核验](../evidence/skill-baseline-equivalence.json)验证改动前后关闭技能的 8 份模型提示、输入、输出 schema 和上限完全相同。此比较非同期执行，改进包含技能指令、上下文精简和局部替换工具，不能把收益仅归因于 SKILL.md。

开发样本数量有限，同一案例的两次运行不能当作两个独立需求；评测没有证明通用能力或统计显著性。所有收益表述必须依据完整报告。

## 部署与兼容

将 `skills/` 与 `ai_service/`、`qa/` 一起发布，并更新包含前端与 Java 字段的 JAR。技能版本发生变动时，尚未完成的新版任务需要保留原包或重新创建，不能静默改用新指令。历史无技能检查点按关闭技能处理，不补造执行历史。

Key 仍由用户在“模型配置”中填写，不需要把凭据放入 Skill。
