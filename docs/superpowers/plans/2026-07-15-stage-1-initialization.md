# Stage 1 Initialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a runnable monorepo skeleton for the customer support ticket automation Agent portfolio project.

**Architecture:** Use a root monorepo with `backend/`, `frontend/`, and infrastructure files. Backend exposes only a health endpoint; frontend renders only a static initialization shell; PostgreSQL and Qdrant are reserved in Docker Compose for later stages.

**Tech Stack:** Python, FastAPI, pytest, React, TypeScript, Vite, PostgreSQL, Qdrant, Docker Compose.

## Global Constraints

- Do not implement Agent, RAG, tool calling, ticket workflow, or frontend business logic in Stage 1.
- Each stage must be independently runnable or testable.
- Do not skip tests.
- Keep code minimal and portfolio-readable.

---

### Task 1: Backend Skeleton

**Files:**
- Create: `backend/tests/test_health.py`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/pyproject.toml`

**Interfaces:**
- Produces: FastAPI app object named `app` in `backend/app/main.py`.
- Produces: `GET /health` returning `{"status": "ok", "service": "kefu-agent-backend"}`.

- [ ] **Step 1: Write the failing health endpoint test**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_service_status() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "kefu-agent-backend",
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest backend/tests -q`

Expected before implementation: failure because `app.main` does not exist.

- [ ] **Step 3: Add the minimal FastAPI app**

```python
from fastapi import FastAPI

app = FastAPI(title="Kefu Agent Backend", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kefu-agent-backend"}
```

- [ ] **Step 4: Run backend tests**

Run: `python -m pytest backend/tests -q`

Expected after implementation: `1 passed`.

### Task 2: Frontend Skeleton

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`

**Interfaces:**
- Produces: Vite React app mounted at `#root`.
- Produces: `npm run dev` and `npm run build` scripts.

- [ ] **Step 1: Add Vite React TypeScript configuration**

Create `package.json`, TypeScript configs, and Vite config with React plugin.

- [ ] **Step 2: Add minimal React entrypoint**

Render a static Stage 1 initialization screen. Do not add API calls or business state.

- [ ] **Step 3: Run frontend build when dependencies are available**

Run: `npm install` then `npm run build` from `frontend/`.

Expected after dependencies install: TypeScript and Vite build succeed.

### Task 3: Root Configuration and Documentation

**Files:**
- Create: `.env.example`
- Create: `docker-compose.yml`
- Create: `README.md`
- Create: `infra/.gitkeep`

**Interfaces:**
- Produces: Docker Compose services `postgres` and `qdrant`.
- Produces: README startup commands for backend, frontend, and infrastructure.

- [ ] **Step 1: Add environment template**

Include backend, frontend, PostgreSQL, and Qdrant defaults.

- [ ] **Step 2: Add Docker Compose skeleton**

Define PostgreSQL 16 and Qdrant services with named volumes and health checks where practical.

- [ ] **Step 3: Add README**

Document project goal, stack, directory structure, startup commands, stage 1 acceptance criteria, and next stage direction.

- [ ] **Step 4: Verify project file structure**

Run: `Get-ChildItem -Recurse -File`

Expected: all Stage 1 files exist.
