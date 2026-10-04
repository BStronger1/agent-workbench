import { writeFile } from "node:fs/promises";
// Reproducible contract fixtures, authored before evaluation. No model outputs in this file.
const scenarios = [
  ["研究任务看板", "研究任务"],
  ["阅读进度记录", "阅读进度"],
  ["实验准备清单", "实验准备"],
  ["项目里程碑", "项目里程碑"],
  ["学习计划页面", "学习计划"],
  ["文献收藏列表", "文献收藏"],
  ["小组活动安排", "小组活动"],
  ["开发任务管理", "开发任务"],
  ["访谈进度页面", "访谈进度"],
  ["数据标注记录", "数据标注"],
  ["会议行动项", "会议行动"],
  ["设备检查清单", "设备检查"],
];
const fixtures = scenarios.flatMap(([title, text], i) =>
  ["none", "window", "retrieval"].map((strategy, j) => ({
    id: `WB-${String(i * 3 + j + 1).padStart(3, "0")}`,
    split: i < 8 ? "dev" : "test",
    prompt: `制作一个${title}，支持点击按钮更新完成数量。`,
    requiredTexts: [text, "项目进度"],
    memoryStrategy: strategy,
    injectFailure: i % 2 === 0,
  })),
);
await writeFile(
  new URL("./fixtures.json", import.meta.url),
  JSON.stringify(fixtures, null, 2) + "\n",
);
