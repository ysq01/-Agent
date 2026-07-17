from collections.abc import Generator

import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import make_engine, make_session_factory
from app.models import Order, OrderItem, Product, Shipment, Ticket, User
from scripts.seed_db import seed_database


TEST_SCHEMA = "kefu_agent_test"


@pytest.fixture(scope="session")
def db_engine() -> Generator[Engine, None, None]:
    admin_engine = make_engine()

    with admin_engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
        connection.execute(text(f"CREATE SCHEMA {TEST_SCHEMA}"))

    engine = make_engine(connect_args={"options": f"-csearch_path={TEST_SCHEMA}"})
    Base.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA} CASCADE"))
        admin_engine.dispose()


@pytest.fixture()
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    session_factory = make_session_factory(db_engine)
    with session_factory() as session:
        yield session


def count_rows(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_database_tables_can_be_created(db_engine: Engine) -> None:
    inspector = inspect(db_engine)

    assert {
        "users",
        "products",
        "orders",
        "order_items",
        "shipments",
        "tickets",
    }.issubset(set(inspector.get_table_names(schema=TEST_SCHEMA)))


def test_seed_database_inserts_expected_records_idempotently(db_session: Session) -> None:
    seed_database(db_session)
    seed_database(db_session)

    assert count_rows(db_session, User) == 30
    assert count_rows(db_session, Product) == 20
    assert count_rows(db_session, Order) == 100
    assert count_rows(db_session, OrderItem) >= 100
    assert count_rows(db_session, Shipment) == 50
    assert count_rows(db_session, Ticket) == 30


def test_seeded_entities_can_be_queried(db_session: Session) -> None:
    seed_database(db_session)

    user = db_session.scalar(select(User).where(User.external_id == "U0001"))
    product = db_session.scalar(select(Product).where(Product.sku == "SKU-0001"))
    order = db_session.scalar(select(Order).where(Order.order_number == "ORD-2026-0001"))
    shipment = db_session.scalar(
        select(Shipment).where(Shipment.tracking_number == "TRK-2026-0001")
    )
    ticket = db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )

    assert user is not None
    assert product is not None
    assert order is not None
    assert shipment is not None
    assert ticket is not None


def test_seeded_relationships_link_core_entities(db_session: Session) -> None:
    seed_database(db_session)

    order = db_session.scalar(select(Order).where(Order.order_number == "ORD-2026-0001"))
    ticket = db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )

    assert order is not None
    assert ticket is not None
    assert order.user is not None
    assert order.user.external_id == "U0001"
    assert len(order.items) >= 1
    assert order.items[0].product is not None
    assert order.items[0].product.sku.startswith("SKU-")
    assert ticket.order == order
    assert ticket.user_id == order.user_id
