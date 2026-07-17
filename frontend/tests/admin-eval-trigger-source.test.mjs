import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const apiSource = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8");
const typeSource = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8");

assert.match(appSource, /生成增强评测/);
assert.match(appSource, /runAdminLlmAssistedEvaluation/);
assert.match(appSource, /getAdminLlmAssistedEvaluationStatus/);
assert.match(appSource, /setInterval/);
assert.match(appSource, /status === "succeeded"/);
assert.match(appSource, /增强模式评测状态获取失败/);
assert.match(apiSource, /\/api\/admin\/eval\/llm-assisted\/run/);
assert.match(apiSource, /\/api\/admin\/eval\/llm-assisted\/status/);
assert.match(typeSource, /AdminEvaluationJobStatusResponse/);
assert.doesNotMatch(appSource, /DASHSCOPE_API_KEY/);

console.log("admin-eval-trigger-source.test.mjs passed");
