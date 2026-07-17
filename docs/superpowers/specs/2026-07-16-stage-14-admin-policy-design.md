# Stage 14 Admin Policy Management Design

## Goal

Add a separated admin management surface for policy document lifecycle management, backed by PostgreSQL authentication and deterministic policy publishing, while preserving the existing customer service workspace, Agent workflow, and rules evaluation baseline.

## Scope

- Add an admin entry in the existing React single-page app.
- Add an admin login page using credentials stored in PostgreSQL.
- Store passwords as PBKDF2 hashes with salts; never store plaintext passwords.
- Store admin session tokens as hashes; never store plaintext tokens in PostgreSQL.
- Add admin policy document CRUD for draft creation, draft/disabled editing, publishing, and disabling.
- Rebuild the Qdrant policy collection after publish or disable using both file-seeded policies and database `published` policies.
- Keep the customer-facing policy knowledge page read-only and limited to published policies.
- Do not change `AgentProcessResponse` shape or Agent workflow node behavior.
- Do not allow LLM-assisted mode to decide policy publication, disablement, or authorization.

## Non-Goals

- No Alembic migration system in this stage; the project continues using `Base.metadata.create_all`.
- No real payment, refund, inventory, or order status changes.
- No automatic policy generation, policy rewriting, model training, or feedback-driven rule updates.
- No new frontend router dependency.
- No token refresh flow; sessions use fixed expiry and logout revocation.
- No fine-grained operator role permissions beyond login/session support unless required by tests.

## Backend Data Model

### `AdminUser`

Table: `admin_users`

- `id`: primary key.
- `username`: unique, indexed, required.
- `password_hash`: required.
- `password_salt`: required.
- `role`: `admin` or `operator`, indexed, required.
- `is_active`: boolean, indexed, required.
- `created_at`: server default timestamp.
- `updated_at`: server default timestamp with `onupdate`.

Password hashing uses Python standard library APIs:

- `secrets.token_hex` for salt.
- `hashlib.pbkdf2_hmac("sha256", ...)` for the hash.
- `hmac.compare_digest` for verification.

### `AdminSession`

Table: `admin_sessions`

- `id`: primary key.
- `token_hash`: unique, indexed, required.
- `admin_user_id`: foreign key to `admin_users.id`, indexed, required.
- `expires_at`: indexed, required.
- `created_at`: server default timestamp.
- `revoked_at`: nullable timestamp.

The login response returns the one-time plaintext token to the browser. Only the hash is persisted.

### `PolicyDocument`

Table: `policy_documents`

- `id`: primary key.
- `title`: required.
- `content`: required.
- `status`: `draft`, `published`, or `disabled`, indexed, required.
- `version`: integer, required, starts at `1`.
- `source`: `admin` or `file_seed`, required, default `admin`.
- `content_hash`: indexed, nullable.
- `created_by`: foreign key to `admin_users.id`, nullable for file/system seed cases.
- `supersedes_policy_id`: nullable self-referential foreign key used when editing a published policy creates a replacement draft.
- `created_at`: server default timestamp.
- `updated_at`: server default timestamp with `onupdate`.
- `published_at`: nullable timestamp.
- `disabled_at`: nullable timestamp.

Only admin-created policies are stored in this table in Stage 14. Existing `data/knowledge` files remain files and are not copied into PostgreSQL.

## Backend API Design

All admin policy APIs require `Authorization: Bearer <token>` except login.

### Auth

`POST /api/admin/login`

Request:

```json
{
  "username": "admin",
  "password": "string"
}
```

Response:

```json
{
  "token": "string",
  "role": "admin",
  "expires_at": "2026-07-17T12:00:00Z"
}
```

Login fails with a generic Chinese business error for unknown users, wrong passwords, inactive users, or expired sessions. It never reveals whether the username exists.

`POST /api/admin/logout`

- Requires bearer token.
- Sets `revoked_at`.
- Returns a small success response.

### Policy Management

`GET /api/admin/policies`

- Requires login.
- Optional query: `status=draft|published|disabled`.
- Returns all admin policy documents visible to management.

`POST /api/admin/policies`

- Requires login.
- Creates a `draft` policy.
- Requires non-empty `title` and `content`.

`PATCH /api/admin/policies/{id}`

- Requires login.
- Allows editing `draft` and `disabled` policies in place.
- Editing a `published` policy creates a new `draft` policy with `version = published.version + 1`, `supersedes_policy_id = published.id`, and leaves the published version active until the replacement is published.

`POST /api/admin/policies/{id}/publish`

- Requires login.
- Publishes a policy.
- Sets `status = "published"` and `published_at`.
- Clears `disabled_at`.
- If the policy has `supersedes_policy_id`, the superseded policy is moved to `disabled` in the same transaction before rebuilding the knowledge collection.
- Rebuilds the Qdrant policy collection from file policies plus all database `published` policies.
- Returns the published policy and an ingestion summary.

`POST /api/admin/policies/{id}/disable`

- Requires login.
- Sets `status = "disabled"` and `disabled_at`.
- Rebuilds the Qdrant policy collection from file policies plus remaining database `published` policies.
- Returns the disabled policy and an ingestion summary.

Qdrant errors are caught at the API boundary and returned as Chinese business messages such as `知识库更新失败，请确认向量服务已启动后重试。` without stack traces, raw payloads, or internal diagnostics.

## Knowledge Source Design

The RAG service becomes a unified published knowledge source.

Sources:

- File policies from `data/knowledge`: always treated as `published`, `source=file_seed`.
- Database policies from `policy_documents`: included only when `status="published"`, `source=admin`.

Qdrant payload fields:

- `policy_title`
- `text`
- `source_file`
- `chunk_index`
- `status`
- `source`
- `policy_id`
- `version`
- `content_hash`

For file policies, `policy_id` is `null`, `source_file` remains the file path, and `version` is `1`.

For admin policies, `source_file` is a stable display-safe value such as `admin-policy-{id}-v{version}`. Customer-facing UI must not display database IDs or payload internals; it only shows title, preview, scenario label, and matched text.

Search behavior:

- Qdrant vector search filters to `status="published"`.
- Keyword fallback also reads only file policies and database `published` policies.
- Draft and disabled policies never appear in customer policy document lists or policy search results.

Ingestion behavior:

- `ingest_knowledge_base(session=...)` can ingest file policies and database `published` policies.
- When no session is supplied, it preserves current file-only script behavior for compatibility.
- Publishing or disabling through admin services calls the full rebuild path with the active database session.
- The rebuild preserves the existing seven file policies and adds/removes only published admin policies.

## Frontend Design

The existing React app remains a state-driven single-page app.

### Navigation

- Extend `PageKey` with `admin`.
- Add a sidebar entry labeled `后台管理`.
- Keep customer service pages unchanged: `客服处理台`, `工单中心`, `政策知识库`, `质检中心`.

### Admin Login

If no admin session token exists in `localStorage`, the admin page shows a login form:

- Username input.
- Password input.
- Submit button.
- Chinese error messages only.

The token is stored in localStorage under an admin-specific key and is never displayed.

### Admin Policy Management

After login, the admin page shows:

- Policy list with title, status, version, update time, publish time.
- Status filter.
- New draft form.
- Draft/disabled editor.
- Read-only preview panel.
- Publish action with confirmation text: `发布后会影响客服政策检索结果，请确认。`
- Disable action with confirmation text: `停用后客服端将不再命中该政策，请确认。`
- Publish success message: `政策已发布，知识库已更新。`
- Disable success message: `政策已停用，客服端将不再命中该政策。`

The UI does not show API paths, tokens, Qdrant payloads, database field names, JSON, or developer diagnostics.

### Customer Policy Knowledge Page

- Continues to call customer-facing knowledge/search APIs.
- Shows only published policies.
- Does not expose edit, publish, disable, token, role, or admin metadata.

## Script Design

Add `backend/scripts/seed_admin.py`.

Behavior:

- Reads `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
- Optional `ADMIN_ROLE`, default `admin`.
- Creates the user if missing.
- Updates password only when explicitly requested with an environment flag such as `ADMIN_RESET_PASSWORD=true`.
- Prints only safe summary text; never prints password, token, salt, or hash.

## Testing Design

Backend tests are written before production code.

Auth tests:

- Successful login returns token, role, and expiry.
- Failed login rejects wrong password.
- Inactive admin cannot login.
- Password is not stored as plaintext.
- Session token is not stored as plaintext.
- Unauthorized requests cannot access admin policy APIs.
- Logout revokes the session.

Policy tests:

- Admin can create a draft policy.
- Admin can edit a draft policy.
- Editing a published policy creates a new draft version and keeps the published version searchable until the replacement is published.
- Publishing a replacement draft disables the superseded published policy so only the new version appears in customer search.
- Draft policies do not appear in customer policy document lists.
- Draft policies do not appear in policy search.
- Published admin policies appear in customer policy document lists.
- Published admin policies can be found by policy search.
- Disabled policies do not appear in customer policy document lists.
- Disabled policies do not appear in policy search.
- Publishing triggers knowledge ingestion or rebuild.
- Disabling triggers knowledge ingestion or rebuild.
- File-seeded policies remain available after publish and disable.

Regression tests:

- Existing `AgentProcessResponse` API shape remains unchanged.
- Existing rules evaluation remains `50 total`, `50 passed`, `0 failed`.
- Frontend build passes.

## Safety Boundaries

- No real refunds.
- No payment status changes.
- No inventory changes.
- No refund status changes.
- No automatic policy changes from Agent, LLM, or feedback data.
- No automatic model training.
- LLM cannot authorize admin actions.
- Customer service users cannot publish or disable policies.
- Admin credentials are never hardcoded in frontend code.
- Passwords, DashScope keys, plaintext tokens, password hashes, and salts are never written to code, docs, tests, logs, or UI.

## Validation Commands

Backend tests:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

Frontend build:

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

Rules evaluation without writing reports:

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

Expected result:

```text
total=50, passed=50, failed=0
```
