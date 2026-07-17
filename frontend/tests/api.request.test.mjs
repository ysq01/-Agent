import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import ts from "typescript";

async function loadApiModule() {
  const source = readFileSync(new URL("../src/api.ts", import.meta.url), "utf8")
    .replaceAll("import.meta.env", "({})");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;

  return import(`data:text/javascript,${encodeURIComponent(compiled)}`);
}

async function testCreateAdminPolicyKeepsJsonContentType() {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(
      JSON.stringify({
        id: 1,
        title: "测试政策",
        content: "测试内容",
        status: "draft",
        version: 1,
        source: "manual",
        supersedes_policy_id: null,
        created_at: "2026-07-16T00:00:00Z",
        updated_at: "2026-07-16T00:00:00Z",
        published_at: null,
        disabled_at: null,
      }),
      {
        status: 201,
        headers: { "Content-Type": "application/json" },
      },
    );
  };

  const api = await loadApiModule();

  await api.createAdminPolicy("admin-token", {
    title: "测试政策",
    content: "测试内容",
  });

  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].init.headers, {
    "Content-Type": "application/json",
    Authorization: "Bearer admin-token",
  });
  assert.equal(
    calls[0].init.body,
    JSON.stringify({ title: "测试政策", content: "测试内容" }),
  );
}

async function testRunAdminLlmAssistedEvaluationKeepsJsonContentType() {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(
      JSON.stringify({
        status: "running",
        message: "增强模式评测正在生成，请稍后查看。",
        started_at: "2026-07-16T16:00:00Z",
        finished_at: null,
        report_generated_at: null,
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  };

  const api = await loadApiModule();
  await api.runAdminLlmAssistedEvaluation("admin-token");

  assert.equal(calls.length, 1);
  assert.equal(
    String(calls[0].url),
    "http://localhost:8000/api/admin/eval/llm-assisted/run",
  );
  assert.deepEqual(calls[0].init.headers, {
    "Content-Type": "application/json",
    Authorization: "Bearer admin-token",
  });
  assert.equal(calls[0].init.method, "POST");
}

async function testListTicketsSendsPaginationParams() {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(
      JSON.stringify({
        total: 30,
        page: 2,
        page_size: 5,
        total_pages: 6,
        tickets: [],
      }),
      {
        status: 200,
        headers: { "Content-Type": "application/json" },
      },
    );
  };

  const api = await loadApiModule();
  await api.listTickets({
    status: "open",
    category: "refund",
    priority: "high",
    page: 2,
    page_size: 5,
  });

  assert.equal(calls.length, 1);
  assert.equal(
    String(calls[0].url),
    "http://localhost:8000/api/tickets?status=open&category=refund&priority=high&page=2&page_size=5",
  );
}

await testCreateAdminPolicyKeepsJsonContentType();
await testRunAdminLlmAssistedEvaluationKeepsJsonContentType();
await testListTicketsSendsPaginationParams();
console.log("api.request.test.mjs passed");
