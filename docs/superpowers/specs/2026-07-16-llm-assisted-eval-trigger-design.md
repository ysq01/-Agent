# LLM-assisted Evaluation Trigger Design

## Goal

Add an admin-only one-click trigger for generating the LLM-assisted evaluation report used by the model comparison page.

The feature should let an administrator start an `llm_assisted` evaluation from the backend management UI, wait for completion, and refresh the existing comparison view once `data/eval/eval_report_llm_assisted.json` is available.

## Non-goals

- Do not let users type, upload, store, or view the DashScope API key in the browser.
- Do not change refund, payment, inventory, policy publishing, or model configuration state.
- Do not automatically tune rules, update policies, train models, or change the active Agent mode.
- Do not expose stack traces, API payloads, tokens, salts, hashes, or provider secrets in API responses or the UI.

## Backend Design

Add admin evaluation job support behind the existing `/api/admin` authorization boundary.

Endpoints:

- `POST /api/admin/eval/llm-assisted/run`: starts a new LLM-assisted evaluation job.
- `GET /api/admin/eval/llm-assisted/status`: returns the current job status.

The run endpoint checks `DASHSCOPE_API_KEY` before starting. If it is missing, return a clear Chinese business error such as `增强模式未配置 API Key，请先在后端环境变量中配置 DASHSCOPE_API_KEY 后重启服务。`

The evaluation runs as a backend background task because 50 cases can take long enough to exceed normal request timeouts. The task should:

- Load the existing evaluation cases.
- Run `run_evaluation(..., mode="llm_assisted")`.
- Use the existing rollback strategy for database writes.
- Write `eval_report_llm_assisted.json`, `eval_report_llm_assisted.md`, and history via `write_evaluation_reports(..., write_history=True)`.
- Record success or failure in an in-memory job status object.

Only one LLM-assisted evaluation job should run at a time. If a job is already running, the run endpoint should return the current running status rather than starting a second job.

## Frontend Design

On the existing admin model comparison page:

- Add a `生成增强评测` button near `刷新对比`.
- Disable it while a generation job is running.
- Poll the status endpoint while the job is running.
- Show short Chinese status text for idle, running, succeeded, failed, and missing-key states.
- On success, automatically refresh the comparison data so the enhanced-mode card and tables populate.

The UI should keep the existing SaaS admin style and avoid exposing internal paths, payloads, traceback text, or provider diagnostics.

## Data Flow

1. Admin clicks `生成增强评测`.
2. Frontend calls the run endpoint with the existing Bearer token.
3. Backend verifies admin session and `DASHSCOPE_API_KEY`.
4. Backend starts a single background evaluation job.
5. Frontend polls status.
6. Backend writes the LLM-assisted report files.
7. Frontend sees success and refreshes `/api/admin/eval/compare`.

## Error Handling

- Missing API key: return a 400-level Chinese message and keep the page usable.
- Existing running job: return running status; do not start duplicate work.
- Evaluation failure: store a sanitized Chinese failure message for the UI.
- Unauthorized admin session: preserve existing admin auth behavior.
- Qdrant or database failure: do not expose stack traces; mark the job failed with a safe message.

## Testing

Backend tests should cover:

- Missing `DASHSCOPE_API_KEY` returns a safe error.
- Run endpoint starts a job for an authorized admin.
- Duplicate run request while running does not start another job.
- Status endpoint returns the expected job shape.
- A successful job writes the LLM-assisted report path through existing report-writing code.

Frontend tests should cover:

- The button is present only on the admin comparison page.
- Clicking the button sends a Bearer request with JSON content type preserved.
- Running state disables the button and shows a Chinese progress message.
- Success refreshes comparison data.
- Missing-key or failed states show safe Chinese messages.

