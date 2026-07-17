# Stage 2 Database Design

## Goal

Build the backend database foundation for the customer support ticket automation Agent without adding AI, Agent orchestration, RAG, or frontend business logic.

## Decisions

- Use PostgreSQL as the formal database.
- Use SQLAlchemy 2.0 ORM and psycopg.
- Read the database connection from `DATABASE_URL`.
- Do not introduce Alembic in this stage.
- Provide `create_all` initialization through a script.
- Use PostgreSQL for pytest tests, not SQLite.
- Use the local development connection `postgresql+psycopg://postgres:123456@localhost:5432/postgres` when `DATABASE_URL` is not set.

## Architecture

The backend adds a small database layer under `backend/app/db/`, SQLAlchemy models under `backend/app/models/`, and operational scripts under `backend/scripts/`.

`backend/app/db/base.py` owns the declarative base. `backend/app/db/session.py` owns database URL normalization, engine construction, and session factory construction. `backend/app/models/` owns the ORM tables and relationships. `backend/scripts/init_db.py` creates tables with `Base.metadata.create_all()`. `backend/scripts/seed_db.py` inserts deterministic seed data idempotently.

## Tables

- `users`: customer identity and contact data.
- `products`: catalog data used by order items.
- `orders`: order header data linked to users.
- `order_items`: line items linked to orders and products.
- `shipments`: logistics records linked to orders.
- `tickets`: customer service tickets linked to orders and users.

## Relationships

- One user has many orders.
- One user has many tickets.
- One order belongs to one user.
- One order has many order items.
- One product has many order items.
- One order has many shipments.
- One order has many tickets.
- One ticket belongs to one order and one user.

## Seed Data

The seed script creates fixed natural keys so repeated runs do not insert duplicates:

- 30 users with `external_id` values `U0001` through `U0030`.
- 20 products with `sku` values `SKU-0001` through `SKU-0020`.
- 100 orders with `order_number` values `ORD-2026-0001` through `ORD-2026-0100`.
- Order items for each seeded order.
- 50 shipments with `tracking_number` values `TRK-2026-0001` through `TRK-2026-0050`.
- 30 tickets with `ticket_number` values `TCK-2026-0001` through `TCK-2026-0030`.

## Testing

Pytest connects to PostgreSQL using the same database URL rules as the scripts. Tests create a dedicated PostgreSQL schema named `kefu_agent_test`, create tables there, seed data there, verify table creation, verify seed counts, query each domain entity, and assert the core relationships.

The test schema is dropped and recreated during the test session to avoid changing seeded development data in the public schema.
