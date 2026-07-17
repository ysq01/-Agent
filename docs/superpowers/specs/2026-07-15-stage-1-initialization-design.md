# Stage 1 Initialization Design

## Goal

Initialize a portfolio-ready monorepo for a customer support ticket automation Agent without implementing Agent, RAG, or business workflow logic yet.

## Scope

Stage 1 creates a runnable project skeleton:

- `backend/`: Python + FastAPI service with a health endpoint and pytest coverage.
- `frontend/`: React + TypeScript + Vite app with a minimal placeholder screen.
- `docker-compose.yml`: PostgreSQL and Qdrant service definitions reserved for later stages.
- `.env.example`: Shared configuration template.
- `README.md`: Project goal, technology stack, and startup instructions.

## Architecture

The repository uses a monorepo layout so backend and frontend can be developed together in VSCode. The backend exposes only `GET /health` in this stage. The frontend renders a static initialization page and does not call backend APIs yet.

PostgreSQL and Qdrant are defined in Docker Compose but not wired into application code. Future stages will add database models, tool calls, RAG indexing/retrieval, state-machine orchestration, execution traces, and an evaluation dashboard.

## Testing

Stage 1 includes a pytest test for the backend health endpoint. The frontend must pass TypeScript compilation through the Vite build script.

## Acceptance Criteria

- Backend health endpoint returns `{"status": "ok", "service": "kefu-agent-backend"}`.
- Backend tests pass with pytest.
- Frontend dependencies and scripts are declared for a Vite React TypeScript app.
- Docker Compose can start PostgreSQL and Qdrant services when Docker is available.
- Documentation explains how to start backend, frontend, and infrastructure.
