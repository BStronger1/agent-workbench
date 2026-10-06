import test from "node:test";
import assert from "node:assert/strict";
import { requireEvaluationMode, evaluationSummary } from "./eval-policy.mjs";
test("live intent cannot fall back to demo", () => {
  assert.throws(
    () =>
      requireEvaluationMode({ mode: "demo", browserValidation: true }, true),
    /不会改跑演示/,
  );
});
test("paid mode needs explicit opt-in and browser verification", () => {
  assert.throws(() =>
    requireEvaluationMode({ mode: "live", browserValidation: true }, false),
  );
  assert.throws(() =>
    requireEvaluationMode({ mode: "live", browserValidation: false }, true),
  );
  assert.doesNotThrow(() =>
    requireEvaluationMode({ mode: "live", browserValidation: true }, true),
  );
});
test("summary separates repair and missing usage", () => {
  const rows = [
    {
      status: "PASSED",
      attempts: [
        { browserStatus: "FAILED", errors: ["button"] },
        { browserStatus: "PASSED", errors: [] },
      ],
      durationMs: 100,
      usageKnown: true,
      inputTokens: 30,
      outputTokens: 40,
    },
  ];
  const result = evaluationSummary(rows);
  assert.equal(result.firstPass, 0);
  assert.equal(result.finalPass, 1);
  assert.equal(result.repairAttempted, 1);
  assert.equal(result.repairSucceeded, 1);
  assert.equal(result.outputTokens, 40);
  rows[0].usageKnown = false;
  assert.equal(evaluationSummary(rows).outputTokens, null);
  assert.equal(evaluationSummary([]).meanDurationMs, null);
});
