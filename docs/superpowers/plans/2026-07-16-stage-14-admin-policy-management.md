# Stage 14 Admin Policy Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separated admin login and policy management surface that publishes PostgreSQL-backed policies into the Qdrant RAG index without changing the existing customer service Agent workflow or safety boundaries.

**Architecture:** Add PostgreSQL admin auth/session tables and policy document tables, expose deterministic FastAPI admin endpoints, and extend the RAG service so published DB policies join the existing file-seeded policies. The React app stays a single-page state machine with a separate admin page and localStorage token handling.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL, Qdrant, Python standard-library PBKDF2, React 18, TypeScript, Vite.

## Global Constraints

- Do not change `AgentProcessResponse` response shape.
- Do not change Agent workflow node order or let LLM authorize admin actions.
- Passwords must be hashed with PBKDF2 and salts; no plaintext password storage.
- Admin session tokens must be hashed in PostgreSQL; no plaintext token storage.
- Customer policy APIs and UI must expose only published policies.
- Draft and disabled policies must not enter customer search.
- Publishing or disabling policies must rebuild Qdrant from `data/knowledge` plus DB `published` policies.
- Keep the existing seven `data/knowledge` policies available.
- Frontend must not show API paths, token values, database field names, Qdrant payloads, JSON, stack traces, or developer diagnostics.
- Do not add a frontend router dependency.
- Do not add heavy password dependencies such as passlib.
- Current workspace is not a git repo; skip commit steps and use verification checkpoints instead.

---

### Task 1: Admin Data Models And Auth Service

**Files:**
- Create: `backend/app/models/admin.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/services/admin_auth.py`
- Create: `backend/tests/test_admin_auth.py`
- Create: `backend/scripts/seed_admin.py`

**Interfaces:**
- Produces `AdminUser`, `AdminSession`.
- Produces `hash_password(password: str) -> tuple[str, str]`.
- Produces `verify_password(password: str, password_hash: str, password_salt: str) -> bool`.
- Produces `create_admin_user(session, username, password, role="admin") -> AdminUser`.
- Produces `authenticate_admin(session, username, password) -> AdminSessionLogin`.
- Produces `get_admin_by_token(session, token) -> AdminUser | None`.
- Produces `revoke_admin_session(session, token) -> bool`.

- [ ] **Step 1: Write failing model/auth tests**

Add tests in `backend/tests/test_admin_auth.py`:

```python
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import AdminSession, AdminUser
from app.services.admin_auth import (
    authenticate_admin,
    create_admin_user,
    get_admin_by_token,
    revoke_admin_session,
    verify_password,
)


def test_admin_password_is_hashed_and_login_returns_plain_token(tools_db_session):
    admin = create_admin_user(tools_db_session, "stage14-admin", "correct-password")

    assert admin.password_hash != "correct-password"
    assert admin.password_salt != "correct-password"
    assert verify_password("correct-password", admin.password_hash, admin.password_salt)

    login = authenticate_admin(tools_db_session, "stage14-admin", "correct-password")

    assert login.token
    assert login.role == "admin"
    assert login.expires_at > datetime.now(UTC)

    stored_session = tools_db_session.scalar(select(AdminSession))
    assert stored_session is not None
    assert stored_session.token_hash != login.token
    assert get_admin_by_token(tools_db_session, login.token).username == "stage14-admin"


def test_admin_login_rejects_wrong_password(tools_db_session):
    create_admin_user(tools_db_session, "stage14-admin", "correct-password")

    assert authenticate_admin(tools_db_session, "stage14-admin", "wrong-password") is None


def test_inactive_admin_cannot_login(tools_db_session):
    admin = create_admin_user(tools_db_session, "stage14-admin", "correct-password")
    admin.is_active = False
    tools_db_session.commit()

    assert authenticate_admin(tools_db_session, "stage14-admin", "correct-password") is None


def test_logout_revokes_admin_session(tools_db_session):
    create_admin_user(tools_db_session, "stage14-admin", "correct-password")
    login = authenticate_admin(tools_db_session, "stage14-admin", "correct-password")

    assert revoke_admin_session(tools_db_session, login.token) is True
    assert get_admin_by_token(tools_db_session, login.token) is None
```

- [ ] **Step 2: Run auth tests and verify RED**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_admin_auth.py -q -p no:cacheprovider
```

Expected: import failures for `AdminUser`, `AdminSession`, and `admin_auth`.

- [ ] **Step 3: Implement models and auth service**

Create SQLAlchemy models with role/status `CheckConstraint`s, PBKDF2 helpers, SHA-256 token hashes, 24-hour session expiry, and generic `None` return for failed authentication.

Create `backend/scripts/seed_admin.py` that reads `ADMIN_USERNAME` and `ADMIN_PASSWORD`, optionally `ADMIN_ROLE` and `ADMIN_RESET_PASSWORD`, and prints only safe summary text.

- [ ] **Step 4: Run auth tests and verify GREEN**

Run the same command. Expected: all auth tests pass.

### Task 2: Admin Auth API

**Files:**
- Create: `backend/app/schemas/admin.py`
- Create: `backend/app/api/admin.py`
- Modify: `backend/app/main.py`
- Extend: `backend/tests/test_admin_auth.py`

**Interfaces:**
- Produces `POST /api/admin/login`.
- Produces `POST /api/admin/logout`.
- Produces `get_current_admin` dependency for later policy APIs.

- [ ] **Step 1: Write failing API tests**

Append tests:

```python
def test_admin_login_api_returns_session_token(tools_client, tools_db_session):
    create_admin_user(tools_db_session, "stage14-admin", "correct-password")

    response = tools_client.post(
        "/api/admin/login",
        json={"username": "stage14-admin", "password": "correct-password"},
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {"token", "role", "expires_at"}
    assert data["role"] == "admin"
    assert data["token"]


def test_admin_login_api_rejects_bad_credentials(tools_client, tools_db_session):
    create_admin_user(tools_db_session, "stage14-admin", "correct-password")

    response = tools_client.post(
        "/api/admin/login",
        json={"username": "stage14-admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert "账号或密码" in response.json()["detail"]


def test_admin_logout_api_revokes_token(tools_client, tools_db_session):
    create_admin_user(tools_db_session, "stage14-admin", "correct-password")
    login = authenticate_admin(tools_db_session, "stage14-admin", "correct-password")

    response = tools_client.post(
        "/api/admin/logout",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 200
    assert get_admin_by_token(tools_db_session, login.token) is None
```

- [ ] **Step 2: Run API tests and verify RED**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_admin_auth.py -q -p no:cacheprovider
```

Expected: `/api/admin/login` not found.

- [ ] **Step 3: Implement schemas/router/main include**

Use Pydantic request/response schemas. Return only Chinese generic auth errors. Include `admin_router` in `backend/app/main.py`.

- [ ] **Step 4: Run API tests and verify GREEN**

Run the same command. Expected: auth API tests pass.

### Task 3: Policy Model And Admin Policy Service

**Files:**
- Create: `backend/app/models/policy.py`
- Modify: `backend/app/models/__init__.py`
- Extend: `backend/app/schemas/admin.py`
- Create: `backend/app/services/admin_policies.py`
- Extend: `backend/app/api/admin.py`
- Create: `backend/tests/test_admin_policies.py`

**Interfaces:**
- Produces `PolicyDocument`.
- Produces `list_admin_policies(session, status=None)`.
- Produces `create_policy(session, request, admin)`.
- Produces `update_policy(session, policy_id, request, admin)`.
- Produces `publish_policy(session, policy_id, admin)`.
- Produces `disable_policy(session, policy_id, admin)`.

- [ ] **Step 1: Write failing policy API tests**

Create tests using helper `login_admin(tools_client, tools_db_session) -> str`:

```python
def test_admin_policy_api_requires_login(tools_client):
    response = tools_client.get("/api/admin/policies")
    assert response.status_code == 401


def test_admin_can_create_and_edit_draft_policy(tools_client, tools_db_session, monkeypatch):
    token = login_admin(tools_client, tools_db_session)

    created = tools_client.post(
        "/api/admin/policies",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "大件商品上门取件规则", "content": "大件商品支持预约上门取件。"},
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]
    assert created.json()["status"] == "draft"

    updated = tools_client.patch(
        f"/api/admin/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "大件商品上门取件规则", "content": "大件商品支持预约上门取件，需提前一天。"},
    )
    assert updated.status_code == 200
    assert "提前一天" in updated.json()["content"]


def test_publish_and_disable_trigger_rebuild(tools_client, tools_db_session, monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.admin_policies.rebuild_knowledge_base", lambda session: calls.append("rebuild"))
    token = login_admin(tools_client, tools_db_session)
    policy_id = create_draft_policy(tools_client, token)

    published = tools_client.post(
        f"/api/admin/policies/{policy_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert published.status_code == 200
    assert published.json()["policy"]["status"] == "published"
    assert calls == ["rebuild"]

    disabled = tools_client.post(
        f"/api/admin/policies/{policy_id}/disable",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["policy"]["status"] == "disabled"
    assert calls == ["rebuild", "rebuild"]


def test_editing_published_policy_creates_replacement_draft(tools_client, tools_db_session, monkeypatch):
    monkeypatch.setattr("app.services.admin_policies.rebuild_knowledge_base", lambda session: None)
    token = login_admin(tools_client, tools_db_session)
    policy_id = create_draft_policy(tools_client, token)
    tools_client.post(f"/api/admin/policies/{policy_id}/publish", headers={"Authorization": f"Bearer {token}"})

    response = tools_client.patch(
        f"/api/admin/policies/{policy_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "新版政策", "content": "新版政策内容"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] != policy_id
    assert data["status"] == "draft"
    assert data["version"] == 2
    assert data["supersedes_policy_id"] == policy_id
```

- [ ] **Step 2: Run policy tests and verify RED**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_admin_policies.py -q -p no:cacheprovider
```

Expected: missing `PolicyDocument` and admin policy endpoints.

- [ ] **Step 3: Implement policy model, schemas, service, and API**

Implement status/source constraints, create/list/update/publish/disable flows, replacement draft behavior, and Qdrant rebuild error translation.

- [ ] **Step 4: Run policy tests and verify GREEN**

Run the same command. Expected: policy API tests pass.

### Task 4: Unified Published Knowledge Source

**Files:**
- Modify: `backend/app/services/policy_knowledge.py`
- Modify: `backend/app/services/knowledge_documents.py`
- Modify: `backend/app/api/knowledge.py`
- Modify: `backend/app/api/tools.py`
- Modify: `backend/app/services/agent_workflow.py`
- Extend: `backend/tests/test_admin_policies.py`
- Extend: `backend/tests/test_policy_knowledge.py`
- Extend: `backend/tests/test_dashboard_read_api.py`

**Interfaces:**
- Extends `load_knowledge_documents(knowledge_dir=None, session=None)`.
- Extends `ingest_knowledge_base(knowledge_dir=None, collection_name=None, session=None)`.
- Adds `rebuild_knowledge_base(session, collection_name=None)`.
- Extends `search_policy(query, top_k=3, collection_name=None, session=None)`.

- [ ] **Step 1: Write failing RAG boundary tests**

Add tests:

```python
def test_customer_knowledge_documents_show_only_published_admin_policies(tools_client, tools_db_session, monkeypatch):
    token = login_admin(tools_client, tools_db_session)
    draft_id = create_draft_policy(tools_client, token, title="后台草稿政策", content="草稿不应展示。")
    monkeypatch.setattr("app.services.admin_policies.rebuild_knowledge_base", lambda session: None)

    before = tools_client.get("/api/knowledge/documents").json()
    assert "后台草稿政策" not in {item["policy_title"] for item in before["documents"]}

    tools_client.post(f"/api/admin/policies/{draft_id}/publish", headers={"Authorization": f"Bearer {token}"})
    after = tools_client.get("/api/knowledge/documents").json()
    assert "后台草稿政策" in {item["policy_title"] for item in after["documents"]}


def test_policy_search_uses_published_admin_policies_and_excludes_disabled(tools_db_session, monkeypatch):
    from app.services.policy_knowledge import search_policy
    from app.models import PolicyDocument

    tools_db_session.add(PolicyDocument(title="后台赔付政策", content="青柠破损可以申请补偿。", status="published", version=1, source="admin"))
    tools_db_session.commit()

    monkeypatch.setattr("app.services.policy_knowledge.make_qdrant_client", lambda: FakeMissingCollectionClient())
    matches = search_policy("青柠破损怎么补偿", session=tools_db_session)
    assert any(match.policy_title == "后台赔付政策" for match in matches)

    policy = tools_db_session.scalar(select(PolicyDocument).where(PolicyDocument.title == "后台赔付政策"))
    policy.status = "disabled"
    tools_db_session.commit()

    matches = search_policy("青柠破损怎么补偿", session=tools_db_session)
    assert all(match.policy_title != "后台赔付政策" for match in matches)
```

Also extend existing dashboard test so the response shape remains exactly `policy_title/source_file/character_count/preview`.

- [ ] **Step 2: Run RAG tests and verify RED**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_admin_policies.py tests\test_policy_knowledge.py tests\test_dashboard_read_api.py -q -p no:cacheprovider
```

Expected: DB policies do not appear yet.

- [ ] **Step 3: Implement unified knowledge source**

Extend document dataclasses with defaulted `status/source/policy_id/version/content_hash` fields. Add DB published document loader. Add Qdrant `status=published` query filter. Ensure fallback keyword search reads file plus DB published policies when a session exists. Make API search and Agent default search pass the current DB session.

- [ ] **Step 4: Run RAG tests and verify GREEN**

Run the same command. Expected: all RAG/admin policy tests pass.

### Task 5: Frontend Admin API Types And Presentation

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/presentation.ts`

**Interfaces:**
- Produces `AdminSessionResponse`, `AdminPolicy`, `AdminPolicyStatus`, `AdminPolicyListResponse`, `AdminPolicyMutationResponse`.
- Produces API functions `adminLogin`, `adminLogout`, `listAdminPolicies`, `createAdminPolicy`, `updateAdminPolicy`, `publishAdminPolicy`, `disableAdminPolicy`.
- Produces `labelPolicyStatus(status)` and `policyStatusTone(status)`.

- [ ] **Step 1: Add frontend types/API wrappers**

Implement typed wrappers with bearer token headers and Chinese-safe error propagation.

- [ ] **Step 2: Run TypeScript build check**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

Expected: build still succeeds or fails only because the UI does not consume new exports yet.

### Task 6: Frontend Admin Login And Policy Management UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Extends `PageKey` with `admin`.
- Adds `AdminPage`, `AdminLoginPanel`, `AdminPolicyManager`.

- [ ] **Step 1: Add admin page state and navigation**

Add sidebar entry `后台管理`, keep existing customer pages unchanged, and display a login form when no admin token is present.

- [ ] **Step 2: Add policy management page**

Implement status filter, policy table, draft editor, preview, publish/disable confirmations, success/error alerts, and logout. Do not display token/API/JSON/internal fields.

- [ ] **Step 3: Add focused styles**

Reuse existing panel/table/form patterns. Add only layout classes needed for admin page, keeping the restrained SaaS styling.

- [ ] **Step 4: Run frontend build**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

Expected: build passes.

### Task 7: Final Verification

**Files:**
- No new production files unless verification reveals defects.

- [ ] **Step 1: Run targeted backend tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_admin_auth.py tests\test_admin_policies.py tests\test_policy_knowledge.py tests\test_dashboard_read_api.py -q -p no:cacheprovider
```

Expected: targeted tests pass.

- [ ] **Step 2: Run full backend test suite**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

Expected: all backend tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

Expected: build passes.

- [ ] **Step 4: Run rules evaluation without writing reports**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
.\.venv\Scripts\python.exe -c "from sqlalchemy.orm import Session; from app.db.session import make_engine; from app.services.evaluation import load_eval_cases, run_evaluation; engine = make_engine(); connection = engine.connect(); transaction = connection.begin(); session = Session(bind=connection, autoflush=False, expire_on_commit=False)
try:
    report = run_evaluation(session, load_eval_cases(), mode='rules')
    print(f'total={report.total_cases}, passed={report.passed_cases}, failed={report.failed_cases}')
finally:
    session.close(); transaction.rollback(); connection.close(); engine.dispose()"
```

Expected:

```text
total=50, passed=50, failed=0
```
