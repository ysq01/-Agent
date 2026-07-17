# LLM-assisted Evaluation Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only button that starts LLM-assisted evaluation generation and refreshes the model comparison page when the report is ready.

**Architecture:** Keep the evaluation execution in a focused backend service with in-memory job state and a single-running-job guard. Expose two admin-authenticated endpoints for starting and polling the job, then wire the existing React comparison page to start the job, poll progress, and refresh `/api/admin/eval/compare` on success.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, existing evaluation service, React + TypeScript + Vite, plain Node regression scripts.

## Global Constraints

- `DASHSCOPE_API_KEY` is read only from backend environment variables.
- Do not let users type, upload, store, or view the DashScope API key in the browser.
- Do not change refund, payment, inventory, policy publishing, or model configuration state.
- Do not automatically tune rules, update policies, train models, or change the active Agent mode.
- Do not expose stack traces, API payloads, tokens, salts, hashes, or provider secrets in API responses or the UI.
- Evaluation-created database writes must use the existing rollback strategy.
- Current workspace is not a git repository; skip commit steps here and rely on test/build evidence.

---

## File Structure

- Modify `backend/app/schemas/evaluation.py`: add the response schema for LLM-assisted evaluation job status.
- Create `backend/app/services/evaluation_jobs.py`: own in-memory status, missing-key checks, one-job-at-a-time guard, and report generation execution.
- Modify `backend/app/api/admin.py`: add admin-only run/status endpoints and map safe business errors to HTTP responses.
- Modify `backend/tests/test_evaluation.py`: add backend service/API coverage with monkeypatches, no real DashScope call.
- Modify `frontend/src/types.ts`: add the job status response type.
- Modify `frontend/src/api.ts`: add admin API helpers for starting and polling the job.
- Modify `frontend/src/App.tsx`: add the button, running state, polling, success refresh, and safe error messages.
- Modify or create `frontend/tests/api.request.test.mjs`: verify new admin POST keeps JSON content type and Bearer token.
- Create `frontend/tests/admin-eval-trigger-source.test.mjs`: source-level regression for button text, API usage, polling, and safe copy.

---

### Task 1: Backend Job Schema

**Files:**
- Modify: `backend/app/schemas/evaluation.py`
- Test: `backend/tests/test_evaluation.py`

**Interfaces:**
- Produces: `EvaluationJobStatusValue = Literal["idle", "running", "succeeded", "failed"]`
- Produces: `LlmAssistedEvaluationJobStatus` with `status`, `message`, `started_at`, `finished_at`, `report_generated_at`

- [ ] **Step 1: Add a failing schema test**

Append this test near the evaluation comparison tests in `backend/tests/test_evaluation.py`:

```python
def test_llm_assisted_eval_job_status_schema_serializes_safe_fields() -> None:
    from app.schemas.evaluation import LlmAssistedEvaluationJobStatus

    status = LlmAssistedEvaluationJobStatus(
        status="running",
        message="增强模式评测正在生成，请稍后查看。",
        started_at=datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
        finished_at=None,
        report_generated_at=None,
    )

    assert status.model_dump(mode="json") == {
        "status": "running",
        "message": "增强模式评测正在生成，请稍后查看。",
        "started_at": "2026-07-16T15:00:00Z",
        "finished_at": None,
        "report_generated_at": None,
    }
```

- [ ] **Step 2: Run the focused backend test to verify it fails**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py::test_llm_assisted_eval_job_status_schema_serializes_safe_fields -q -p no:cacheprovider
```

Expected: FAIL because `LlmAssistedEvaluationJobStatus` is not defined.

- [ ] **Step 3: Add the schema**

In `backend/app/schemas/evaluation.py`, update imports and add this after `EvaluationLlmStatus`:

```python
EvaluationJobStatusValue = Literal["idle", "running", "succeeded", "failed"]


class LlmAssistedEvaluationJobStatus(EvaluationSchema):
    status: EvaluationJobStatusValue
    message: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    report_generated_at: datetime | None = None
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py::test_llm_assisted_eval_job_status_schema_serializes_safe_fields -q -p no:cacheprovider
```

Expected: PASS.

---

### Task 2: Backend Evaluation Job Service

**Files:**
- Create: `backend/app/services/evaluation_jobs.py`
- Modify: `backend/tests/test_evaluation.py`

**Interfaces:**
- Consumes: `LlmAssistedEvaluationJobStatus`
- Produces: `EvaluationJobStartResult(status: LlmAssistedEvaluationJobStatus, started: bool)`
- Produces: `EvaluationJobError(message: str)`
- Produces: `get_llm_assisted_evaluation_status() -> LlmAssistedEvaluationJobStatus`
- Produces: `start_llm_assisted_evaluation_job() -> EvaluationJobStartResult`
- Produces: `run_llm_assisted_evaluation_job() -> None`
- Produces: `reset_llm_assisted_evaluation_job_for_tests() -> None`

- [ ] **Step 1: Add failing service tests**

Append these tests to `backend/tests/test_evaluation.py`:

```python
def test_llm_assisted_eval_job_rejects_missing_api_key(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with pytest.raises(evaluation_jobs.EvaluationJobError) as error:
        evaluation_jobs.start_llm_assisted_evaluation_job()

    assert "DASHSCOPE_API_KEY" in str(error.value)
    assert evaluation_jobs.get_llm_assisted_evaluation_status().status == "idle"


def test_llm_assisted_eval_job_allows_only_one_running_job(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    first = evaluation_jobs.start_llm_assisted_evaluation_job()
    second = evaluation_jobs.start_llm_assisted_evaluation_job()

    assert first.started is True
    assert first.status.status == "running"
    assert second.started is False
    assert second.status.status == "running"


def test_llm_assisted_eval_job_records_success(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    generated_at = datetime(2026, 7, 16, 15, 30, tzinfo=UTC)

    class FakeReport:
        def __init__(self) -> None:
            self.generated_at = generated_at

    monkeypatch.setattr(
        evaluation_jobs,
        "_execute_llm_assisted_evaluation",
        lambda: FakeReport(),
    )

    start = evaluation_jobs.start_llm_assisted_evaluation_job()
    evaluation_jobs.run_llm_assisted_evaluation_job()
    status = evaluation_jobs.get_llm_assisted_evaluation_status()

    assert start.started is True
    assert status.status == "succeeded"
    assert status.report_generated_at == generated_at
    assert "已生成" in status.message


def test_llm_assisted_eval_job_records_safe_failure(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    def fail() -> None:
        raise RuntimeError("provider payload with secret")

    monkeypatch.setattr(evaluation_jobs, "_execute_llm_assisted_evaluation", fail)

    evaluation_jobs.start_llm_assisted_evaluation_job()
    evaluation_jobs.run_llm_assisted_evaluation_job()
    status = evaluation_jobs.get_llm_assisted_evaluation_status()

    assert status.status == "failed"
    assert "生成失败" in status.message
    assert "secret" not in status.message
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py -q -p no:cacheprovider
```

Expected: FAIL because `app.services.evaluation_jobs` does not exist.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/evaluation_jobs.py`:

```python
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.session import make_engine
from app.schemas.evaluation import (
    EvaluationReport,
    LlmAssistedEvaluationJobStatus,
)
from app.services.evaluation import (
    DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH,
    DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH,
    load_eval_cases,
    run_evaluation,
    write_evaluation_reports,
)


MISSING_API_KEY_MESSAGE = (
    "增强模式未配置 API Key，请先在后端环境变量中配置 "
    "DASHSCOPE_API_KEY 后重启服务。"
)
IDLE_MESSAGE = "尚未触发增强模式评测。"
RUNNING_MESSAGE = "增强模式评测正在生成，请稍后查看。"
SUCCEEDED_MESSAGE = "增强模式评测已生成，正在刷新对比结果。"
FAILED_MESSAGE = "增强模式评测生成失败，请检查后端评测依赖后重试。"


class EvaluationJobError(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationJobStartResult:
    status: LlmAssistedEvaluationJobStatus
    started: bool


_lock = threading.Lock()
_job_status = LlmAssistedEvaluationJobStatus(
    status="idle",
    message=IDLE_MESSAGE,
)


def get_llm_assisted_evaluation_status() -> LlmAssistedEvaluationJobStatus:
    with _lock:
        return _job_status.model_copy(deep=True)


def start_llm_assisted_evaluation_job() -> EvaluationJobStartResult:
    if not os.getenv("DASHSCOPE_API_KEY", "").strip():
        raise EvaluationJobError(MISSING_API_KEY_MESSAGE)

    global _job_status
    now = datetime.now(UTC)
    with _lock:
        if _job_status.status == "running":
            return EvaluationJobStartResult(
                status=_job_status.model_copy(deep=True),
                started=False,
            )

        _job_status = LlmAssistedEvaluationJobStatus(
            status="running",
            message=RUNNING_MESSAGE,
            started_at=now,
            finished_at=None,
            report_generated_at=None,
        )
        return EvaluationJobStartResult(
            status=_job_status.model_copy(deep=True),
            started=True,
        )


def run_llm_assisted_evaluation_job() -> None:
    global _job_status
    try:
        report = _execute_llm_assisted_evaluation()
    except Exception:
        with _lock:
            _job_status = _job_status.model_copy(
                update={
                    "status": "failed",
                    "message": FAILED_MESSAGE,
                    "finished_at": datetime.now(UTC),
                },
                deep=True,
            )
        return

    with _lock:
        _job_status = _job_status.model_copy(
            update={
                "status": "succeeded",
                "message": SUCCEEDED_MESSAGE,
                "finished_at": datetime.now(UTC),
                "report_generated_at": report.generated_at,
            },
            deep=True,
        )


def _execute_llm_assisted_evaluation() -> EvaluationReport:
    cases = load_eval_cases()
    engine = make_engine()
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
            )
            try:
                report = run_evaluation(session, cases, mode="llm_assisted")
            finally:
                session.close()
                transaction.rollback()

        write_evaluation_reports(
            report,
            json_path=DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH,
            markdown_path=DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH,
            write_history=True,
        )
        return report
    finally:
        engine.dispose()


def reset_llm_assisted_evaluation_job_for_tests() -> None:
    global _job_status
    with _lock:
        _job_status = LlmAssistedEvaluationJobStatus(
            status="idle",
            message=IDLE_MESSAGE,
        )
```

- [ ] **Step 4: Run service tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py -q -p no:cacheprovider
```

Expected: PASS for existing evaluation tests and the new service tests.

---

### Task 3: Admin API Endpoints

**Files:**
- Modify: `backend/app/api/admin.py`
- Modify: `backend/tests/test_evaluation.py`

**Interfaces:**
- Consumes: `evaluation_jobs.start_llm_assisted_evaluation_job()`
- Consumes: `evaluation_jobs.run_llm_assisted_evaluation_job()`
- Produces: `POST /api/admin/eval/llm-assisted/run`
- Produces: `GET /api/admin/eval/llm-assisted/status`

- [ ] **Step 1: Add failing API tests**

Append these tests to `backend/tests/test_evaluation.py`:

```python
def test_admin_llm_eval_run_requires_login(tools_client: TestClient) -> None:
    response = tools_client.post("/api/admin/eval/llm-assisted/run")

    assert response.status_code == 401


def test_admin_llm_eval_status_requires_login(tools_client: TestClient) -> None:
    response = tools_client.get("/api/admin/eval/llm-assisted/status")

    assert response.status_code == 401


def test_admin_llm_eval_run_reports_missing_key(
    tools_client: TestClient,
    tools_db_session,
    monkeypatch,
) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    create_admin_user(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    assert login is not None

    response = tools_client.post(
        "/api/admin/eval/llm-assisted/run",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 400
    assert "DASHSCOPE_API_KEY" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_admin_llm_eval_run_starts_background_job(
    tools_client: TestClient,
    tools_db_session,
    monkeypatch,
) -> None:
    from app.schemas.evaluation import LlmAssistedEvaluationJobStatus
    from app.services.evaluation_jobs import EvaluationJobStartResult

    create_admin_user(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    assert login is not None
    calls: list[str] = []

    def fake_start() -> EvaluationJobStartResult:
        return EvaluationJobStartResult(
            status=LlmAssistedEvaluationJobStatus(
                status="running",
                message="增强模式评测正在生成，请稍后查看。",
                started_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
            ),
            started=True,
        )

    def fake_run() -> None:
        calls.append("run")

    monkeypatch.setattr(
        "app.api.admin.evaluation_jobs.start_llm_assisted_evaluation_job",
        fake_start,
    )
    monkeypatch.setattr(
        "app.api.admin.evaluation_jobs.run_llm_assisted_evaluation_job",
        fake_run,
    )

    response = tools_client.post(
        "/api/admin/eval/llm-assisted/run",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert calls == ["run"]


def test_admin_llm_eval_status_returns_current_job(
    tools_client: TestClient,
    tools_db_session,
    monkeypatch,
) -> None:
    from app.schemas.evaluation import LlmAssistedEvaluationJobStatus

    create_admin_user(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    assert login is not None

    monkeypatch.setattr(
        "app.api.admin.evaluation_jobs.get_llm_assisted_evaluation_status",
        lambda: LlmAssistedEvaluationJobStatus(
            status="succeeded",
            message="增强模式评测已生成，正在刷新对比结果。",
            started_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
            finished_at=datetime(2026, 7, 16, 16, 2, tzinfo=UTC),
            report_generated_at=datetime(2026, 7, 16, 16, 2, tzinfo=UTC),
        ),
    )

    response = tools_client.get(
        "/api/admin/eval/llm-assisted/status",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert "已生成" in response.json()["message"]
```

- [ ] **Step 2: Run focused API tests to verify they fail**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py::test_admin_llm_eval_run_requires_login tests\test_evaluation.py::test_admin_llm_eval_status_requires_login tests\test_evaluation.py::test_admin_llm_eval_run_reports_missing_key tests\test_evaluation.py::test_admin_llm_eval_run_starts_background_job tests\test_evaluation.py::test_admin_llm_eval_status_returns_current_job -q -p no:cacheprovider
```

Expected: FAIL with 404 for the new endpoints.

- [ ] **Step 3: Add endpoints**

In `backend/app/api/admin.py`, update imports:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from app.schemas.evaluation import EvaluationCompareResponse, LlmAssistedEvaluationJobStatus
from app.services import evaluation_jobs
from app.services.evaluation_jobs import EvaluationJobError
```

Add routes after `compare_evaluation_reports`:

```python
@router.post(
    "/eval/llm-assisted/run",
    response_model=LlmAssistedEvaluationJobStatus,
)
def run_llm_assisted_evaluation(
    background_tasks: BackgroundTasks,
    _admin: CurrentAdmin,
) -> LlmAssistedEvaluationJobStatus:
    try:
        result = evaluation_jobs.start_llm_assisted_evaluation_job()
    except EvaluationJobError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    if result.started:
        background_tasks.add_task(evaluation_jobs.run_llm_assisted_evaluation_job)
    return result.status


@router.get(
    "/eval/llm-assisted/status",
    response_model=LlmAssistedEvaluationJobStatus,
)
def get_llm_assisted_evaluation_status(
    _admin: CurrentAdmin,
) -> LlmAssistedEvaluationJobStatus:
    return evaluation_jobs.get_llm_assisted_evaluation_status()
```

- [ ] **Step 4: Run backend evaluation tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py -q -p no:cacheprovider
```

Expected: PASS.

---

### Task 4: Frontend API Types and Helpers

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/tests/api.request.test.mjs`

**Interfaces:**
- Consumes: `POST /api/admin/eval/llm-assisted/run`
- Consumes: `GET /api/admin/eval/llm-assisted/status`
- Produces: `AdminEvaluationJobStatusResponse`
- Produces: `runAdminLlmAssistedEvaluation(token: string)`
- Produces: `getAdminLlmAssistedEvaluationStatus(token: string)`

- [ ] **Step 1: Add failing frontend API test**

In `frontend/tests/api.request.test.mjs`, append:

```javascript
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

await testRunAdminLlmAssistedEvaluationKeepsJsonContentType();
```

- [ ] **Step 2: Run the API test to verify it fails**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
node tests\api.request.test.mjs
```

Expected: FAIL because `runAdminLlmAssistedEvaluation` is not exported.

- [ ] **Step 3: Add frontend type**

In `frontend/src/types.ts`, after `EvaluationLlmStatus`, add:

```typescript
export type AdminEvaluationJobStatusValue =
  | "idle"
  | "running"
  | "succeeded"
  | "failed";

export type AdminEvaluationJobStatusResponse = {
  status: AdminEvaluationJobStatusValue;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  report_generated_at: string | null;
};
```

- [ ] **Step 4: Add API helpers**

In `frontend/src/api.ts`, import `AdminEvaluationJobStatusResponse`, then add:

```typescript
export function runAdminLlmAssistedEvaluation(
  token: string,
): Promise<AdminEvaluationJobStatusResponse> {
  return fetchJson<AdminEvaluationJobStatusResponse>(
    "/api/admin/eval/llm-assisted/run",
    {
      method: "POST",
      headers: bearerHeaders(token),
    },
  );
}

export function getAdminLlmAssistedEvaluationStatus(
  token: string,
): Promise<AdminEvaluationJobStatusResponse> {
  return fetchJson<AdminEvaluationJobStatusResponse>(
    "/api/admin/eval/llm-assisted/status",
    {
      headers: bearerHeaders(token),
    },
  );
}
```

- [ ] **Step 5: Run the frontend API test**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
node tests\api.request.test.mjs
```

Expected: PASS.

---

### Task 5: Frontend Comparison Page Trigger UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/tests/admin-eval-trigger-source.test.mjs`

**Interfaces:**
- Consumes: `runAdminLlmAssistedEvaluation`
- Consumes: `getAdminLlmAssistedEvaluationStatus`
- Consumes: `AdminEvaluationJobStatusResponse`
- Produces: `生成增强评测` UI, polling, success refresh

- [ ] **Step 1: Add failing source regression test**

Create `frontend/tests/admin-eval-trigger-source.test.mjs`:

```javascript
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
```

- [ ] **Step 2: Run the source test to verify it fails**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
node tests\admin-eval-trigger-source.test.mjs
```

Expected: FAIL because the UI is not wired yet.

- [ ] **Step 3: Wire imports and state**

In `frontend/src/App.tsx`, add imports:

```typescript
  getAdminLlmAssistedEvaluationStatus,
  runAdminLlmAssistedEvaluation,
```

Add type import:

```typescript
  AdminEvaluationJobStatusResponse,
```

Inside `AdminEvaluationComparePage`, add state:

```typescript
  const [generationStatus, setGenerationStatus] =
    useState<AdminEvaluationJobStatusResponse | null>(null);
  const [isStartingGeneration, setIsStartingGeneration] = useState(false);
```

- [ ] **Step 4: Add status loading and polling**

Inside `AdminEvaluationComparePage`, add:

```typescript
  useEffect(() => {
    void loadGenerationStatus();
  }, [session.token]);

  useEffect(() => {
    if (generationStatus?.status !== "running") {
      return;
    }

    const timer = window.setInterval(() => {
      void pollGenerationStatus();
    }, 3000);

    return () => window.clearInterval(timer);
  }, [generationStatus?.status, session.token]);

  async function loadGenerationStatus() {
    try {
      setGenerationStatus(
        await getAdminLlmAssistedEvaluationStatus(session.token),
      );
    } catch {
      setGenerationStatus(null);
    }
  }

  async function pollGenerationStatus() {
    try {
      const nextStatus = await getAdminLlmAssistedEvaluationStatus(session.token);
      setGenerationStatus(nextStatus);
      if (nextStatus.status === "succeeded") {
        await loadComparison();
      }
    } catch {
      setGenerationStatus({
        status: "failed",
        message: "增强模式评测状态获取失败，请稍后刷新页面重试。",
        started_at: generationStatus?.started_at ?? null,
        finished_at: null,
        report_generated_at: null,
      });
    }
  }
```

- [ ] **Step 5: Add start handler**

Inside `AdminEvaluationComparePage`, add:

```typescript
  async function startLlmAssistedEvaluation() {
    setIsStartingGeneration(true);
    setError(null);
    try {
      const nextStatus = await runAdminLlmAssistedEvaluation(session.token);
      setGenerationStatus(nextStatus);
      if (nextStatus.status === "succeeded") {
        await loadComparison();
      }
    } catch (caughtError) {
      setGenerationStatus({
        status: "failed",
        message:
          caughtError instanceof Error
            ? caughtError.message
            : "增强模式评测启动失败，请稍后重试。",
        started_at: null,
        finished_at: null,
        report_generated_at: null,
      });
    } finally {
      setIsStartingGeneration(false);
    }
  }
```

- [ ] **Step 6: Render button and safe status**

Replace the single refresh button in the `panel-heading` with:

```tsx
          <div className="compare-actions">
            <button
              className="secondary-button"
              disabled={
                isLoading ||
                isStartingGeneration ||
                generationStatus?.status === "running" ||
                comparison?.llm_status.configured === false
              }
              onClick={() => void startLlmAssistedEvaluation()}
              type="button"
            >
              {generationStatus?.status === "running" || isStartingGeneration
                ? "生成中..."
                : "生成增强评测"}
            </button>
            <button
              className="primary-button"
              disabled={isLoading}
              onClick={() => void loadComparison()}
              type="button"
            >
              {isLoading ? "刷新中..." : "刷新对比"}
            </button>
          </div>
```

Render below the existing `error` block:

```tsx
        {generationStatus && generationStatus.status !== "idle" && (
          <div
            className={
              generationStatus.status === "failed"
                ? "alert error"
                : "health-banner compare-status-banner"
            }
          >
            {generationStatus.message}
          </div>
        )}
```

- [ ] **Step 7: Add minimal action layout CSS if needed**

If `frontend/src/styles.css` does not already have a suitable action wrapper, add:

```css
.compare-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: flex-end;
}
```

- [ ] **Step 8: Run frontend tests**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
node tests\api.request.test.mjs
node tests\admin-eval-trigger-source.test.mjs
node tests\admin-layout-css.test.mjs
node tests\knowledge-page-source.test.mjs
```

Expected: all pass.

---

### Task 6: Full Verification

**Files:**
- Verify only; no source files modified in this task.

**Interfaces:**
- Consumes all previous tasks.
- Produces final evidence that backend tests and frontend build still pass.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py tests\test_admin_auth.py -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 2: Run full backend tests if local database services are available**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

Expected: PASS. If PostgreSQL/Qdrant are unavailable, report the exact failure and keep the focused tests as the verified baseline.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Run frontend regression scripts**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
node tests\api.request.test.mjs
node tests\admin-eval-trigger-source.test.mjs
node tests\admin-layout-css.test.mjs
node tests\knowledge-page-source.test.mjs
```

Expected: all pass.

- [ ] **Step 5: Manual smoke path**

Start the backend with `DASHSCOPE_API_KEY` configured in the backend shell, log into the admin page, open `模型效果对比`, click `生成增强评测`, confirm the button changes to `生成中...`, wait for success, and confirm the enhanced-mode card no longer shows `暂无增强模式评测报告`.

---

## Self-Review

- Spec coverage: admin-only trigger, backend env key, background status polling, one running job, rollback evaluation, safe Chinese errors, and no browser key handling are covered by Tasks 2-5.
- Placeholder scan: no unresolved placeholder markers or undefined future work remains.
- Type consistency: backend `LlmAssistedEvaluationJobStatus` maps directly to frontend `AdminEvaluationJobStatusResponse`; endpoint paths are identical in backend, frontend API helpers, and tests.
- Scope check: the plan only adds report generation and status UI; it does not alter policies, rules, model defaults, refunds, payments, inventory, or training.
