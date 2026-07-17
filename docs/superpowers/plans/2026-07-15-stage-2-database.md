# Stage 2 Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SQLAlchemy 2.0 PostgreSQL models, initialization, idempotent seed data, and pytest coverage for stage 2.

**Architecture:** Add focused backend database modules for configuration, base metadata, sessions, ORM models, and scripts. Tests use a dedicated PostgreSQL schema so they validate real PostgreSQL behavior without touching public development data.

**Tech Stack:** Python 3.13.2, FastAPI, SQLAlchemy 2.0, psycopg 3, PostgreSQL 18.4, pytest.

## Global Constraints

- Do not add AI, Agent, RAG, or frontend business logic.
- Use PostgreSQL as the formal database.
- Read `DATABASE_URL` from environment variables.
- Do not introduce Alembic in this stage.
- Use `Base.metadata.create_all()` for initialization.
- Seed data must be idempotent.
- Pytest must use PostgreSQL, not SQLite.
- Preserve the stage 1 `/health` endpoint and frontend build.

---

### Task 1: Dependencies And Database Layer

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/base.py`
- Create: `backend/app/db/session.py`

**Interfaces:**
- Produces: `Base`, `DEFAULT_DATABASE_URL`, `normalize_database_url(database_url: str) -> str`, `get_database_url() -> str`, `make_engine(database_url: str | None = None, **kwargs) -> Engine`, `make_session_factory(engine: Engine) -> sessionmaker[Session]`

- [ ] Add SQLAlchemy and psycopg dependencies.
- [ ] Fix the existing dev dependency from `httpx2` to `httpx`.
- [ ] Add database URL normalization so `postgresql://` URLs use the psycopg driver as `postgresql+psycopg://`.
- [ ] Add engine and session factory helpers.

### Task 2: ORM Models

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/product.py`
- Create: `backend/app/models/order.py`
- Create: `backend/app/models/shipment.py`
- Create: `backend/app/models/ticket.py`

**Interfaces:**
- Consumes: `Base`
- Produces: SQLAlchemy ORM classes `User`, `Product`, `Order`, `OrderItem`, `Shipment`, `Ticket`

- [ ] Write failing tests for required table names and relationships.
- [ ] Implement typed SQLAlchemy 2.0 models with primary keys, unique natural keys, timestamps, foreign keys, and relationships.
- [ ] Re-run the table creation tests against PostgreSQL.

### Task 3: Initialization And Seed Scripts

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/init_db.py`
- Create: `backend/scripts/seed_db.py`

**Interfaces:**
- Consumes: `Base`, `make_engine`, `make_session_factory`, ORM classes
- Produces: `init_database(database_url: str | None = None) -> None`, `seed_database(session: Session) -> SeedSummary`

- [ ] Write failing tests for seed counts and idempotency.
- [ ] Implement `init_db.py` using `Base.metadata.create_all()`.
- [ ] Implement deterministic seed data with natural-key checks.
- [ ] Re-run seed tests against PostgreSQL.

### Task 4: Documentation And Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Test: `backend/tests/test_health.py`
- Test: `backend/tests/test_database.py`

**Interfaces:**
- Consumes: scripts and models from earlier tasks.
- Produces: documented initialization and testing commands.

- [ ] Add stage 2 database commands to README.
- [ ] Update `.env.example` for the local PostgreSQL password confirmed by the user.
- [ ] Run database initialization against local PostgreSQL.
- [ ] Run seed against local PostgreSQL.
- [ ] Run backend pytest.
- [ ] Run frontend build to confirm stage 1 remains runnable.
