export function requireEvaluationMode(config, liveRequested) {
  if (liveRequested && config.mode !== "live")
    throw new Error(
      "真实评测已停止：当前空间没有启用真实模型。请先配置模型和 API Key；不会改跑演示。 ",
    );
  if (!liveRequested && config.mode === "live")
    throw new Error("真实模型调用需要显式 --live，并会产生 API 费用。");
  if (!config.browserValidation) throw new Error("评测需要启用浏览器验收。");
}

export function evaluationSummary(rows) {
  // Failed provider calls can be charged without returning usable usage metadata.
  const known = rows.length > 0 && rows.every((r) => r.usageKnown && r.status === "PASSED");
  return {
    count: rows.length,
    firstPass: rows.filter(
      (r) =>
        r.attempts[0]?.browserStatus === "PASSED" &&
        r.attempts[0]?.errors?.length === 0,
    ).length,
    finalPass: rows.filter((r) => r.status === "PASSED").length,
    repairAttempted: rows.filter((r) => r.attempts.length > 1 || r.events?.some(e => e.stage === "repair")).length,
    repairSucceeded: rows.filter(
      (r) => r.attempts.length > 1 && r.status === "PASSED",
    ).length,
    meanAttempts: rows.length
      ? rows.reduce((s, r) => s + r.attempts.length, 0) / rows.length
      : null,
    meanDurationMs: rows.length
      ? rows.reduce((s, r) => s + r.durationMs, 0) / rows.length
      : null,
    usageKnown: known,
    inputTokens: known ? rows.reduce((s, r) => s + r.inputTokens, 0) : null,
    outputTokens: known ? rows.reduce((s, r) => s + r.outputTokens, 0) : null,
  };
}
