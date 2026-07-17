# Stage 4 RAG Policy Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Qdrant-backed local policy knowledge ingestion and retrieval.

**Architecture:** Keep the new RAG retrieval surface independent from Agent orchestration. A focused service module reads policy files, embeds chunks locally, writes them to Qdrant, and searches them; the existing tools API exposes only the search tool.

**Tech Stack:** FastAPI, Pydantic, pytest, qdrant-client, fastembed, local Markdown/text documents.

## Global Constraints

- Do not implement a full Agent.
- Do not integrate a Chat LLM.
- Do not generate final customer-facing answers.
- Use Qdrant as the vector database.
- Prefer fastembed for local embeddings and avoid OpenAI API keys.
- Keep all existing stage 1, 2, and 3 behavior working.

---

### Task 1: Tests First

**Files:**
- Create: `backend/tests/test_policy_knowledge.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Consumes: future `app.services.policy_knowledge.ingest_knowledge_base`
- Consumes: future `app.services.policy_knowledge.search_policy`
- Produces: regression checks for import, retrieval, and route response fields.

- [ ] Write tests for idempotent ingestion into a real Qdrant test collection.
- [ ] Write tests for queries matching seven-day return and logistics-delay policies.
- [ ] Write a route test for `POST /api/tools/policies/search`.
- [ ] Run the test file and verify it fails because the service and route do not exist yet.

### Task 2: Knowledge Documents

**Files:**
- Create: `data/knowledge/seven_day_return.md`
- Create: `data/knowledge/special_goods_return.md`
- Create: `data/knowledge/logistics_delay_compensation.md`
- Create: `data/knowledge/invoice_rules.md`
- Create: `data/knowledge/member_after_sales_rights.md`
- Create: `data/knowledge/complaint_escalation.md`
- Create: `data/knowledge/refund_arrival_time.md`

**Interfaces:**
- Produces: local `.md` source documents for ingestion.

- [ ] Add concise Chinese policy documents with clear first-level titles.

### Task 3: Service and Script

**Files:**
- Create: `backend/app/services/policy_knowledge.py`
- Create: `backend/scripts/ingest_knowledge.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Produces: `KnowledgeIngestionResult`
- Produces: `ingest_knowledge_base(knowledge_dir: Path | None = None, collection_name: str | None = None) -> KnowledgeIngestionResult`
- Produces: `search_policy(query: str, top_k: int = 3, collection_name: str | None = None) -> list[PolicySearchMatch]`

- [ ] Add qdrant-client and fastembed dependencies.
- [ ] Implement document loading, title extraction, chunking, local embedding, collection creation, source-file cleanup, and point upsert.
- [ ] Implement script entry point that prints import counts.

### Task 4: API Wiring

**Files:**
- Modify: `backend/app/schemas/tools.py`
- Modify: `backend/app/api/tools.py`

**Interfaces:**
- Produces: `PolicySearchRequest`
- Produces: `PolicySearchResponse`
- Produces: `POST /api/tools/policies/search`

- [ ] Add Pydantic request and response schemas.
- [ ] Add route that calls the service and returns `tool_name="search_policy"`.

### Task 5: Verification

**Files:**
- Modify: `README.md`
- Optional modify: `.env.example`

**Interfaces:**
- Produces: user-facing commands for ingestion and search.

- [ ] Run the policy knowledge tests.
- [ ] Run existing backend tests.
- [ ] Run frontend build.
- [ ] Run docker compose config.
- [ ] Document import and search commands.
