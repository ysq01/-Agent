# Stage 4 RAG Policy Search Design

## Goal

Build a Qdrant-backed policy knowledge import and search tool for the customer service Agent project. This stage imports local policy documents and retrieves matching policy chunks only; it does not implement an Agent, LangGraph workflow, Chat LLM call, or generated answer.

## Scope

- Read `.md` and `.txt` documents from `data/knowledge`.
- Extract each document title from the first Markdown heading or first non-empty line.
- Split documents into overlapping text chunks.
- Embed chunks with a local embedding provider, preferring `fastembed`.
- Store chunks in Qdrant collection `kefu_policy_chunks` by default.
- Provide idempotent ingestion through `backend/scripts/ingest_knowledge.py`.
- Provide `search_policy` through `POST /api/tools/policies/search`.
- Use a real Qdrant test collection for pytest coverage.

## Architecture

The implementation follows the existing backend shape. `app.services.policy_knowledge` owns document loading, chunking, embedding, Qdrant collection management, ingestion, and retrieval. `app.schemas.tools` adds request and response models for policy search. `app.api.tools` exposes the FastAPI route and delegates to the service layer.

Qdrant connection settings come from environment variables:

- `QDRANT_URL`, default `http://localhost:6333`
- `QDRANT_COLLECTION`, default `kefu_policy_chunks`
- `KEFU_EMBEDDING_MODEL`, default `Qdrant/paraphrase-multilingual-MiniLM-L12-v2`

## Data Model

Each Qdrant point payload contains:

- `policy_title`
- `text`
- `source_file`
- `chunk_index`

Search responses return:

- `policy_title`
- `matched_text`
- `score`
- `source_file`

## Idempotency

Ingestion deletes existing points for each source file before writing that file's current chunks. Re-running the script therefore refreshes changed files and avoids duplicate or stale chunks for the same source.

## Testing

Tests use real Qdrant with a dedicated collection name. They cover successful import, retrieval for seven-day return and logistics-delay compensation queries, and response field shape from the FastAPI route.
