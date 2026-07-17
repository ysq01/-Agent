from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import make_engine, make_session_factory
from app.main import app
from scripts.seed_db import seed_database


TOOLS_TEST_SCHEMA = "kefu_agent_tools_test"


@pytest.fixture(scope="session")
def tools_db_engine() -> Generator[Engine, None, None]:
    admin_engine = make_engine()

    with admin_engine.begin() as connection:
        connection.execute(text(f"DROP SCHEMA IF EXISTS {TOOLS_TEST_SCHEMA} CASCADE"))
        connection.execute(text(f"CREATE SCHEMA {TOOLS_TEST_SCHEMA}"))

    engine = make_engine(connect_args={"options": f"-csearch_path={TOOLS_TEST_SCHEMA}"})

    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {TOOLS_TEST_SCHEMA} CASCADE"))
        admin_engine.dispose()


@pytest.fixture()
def seeded_tools_db(tools_db_engine: Engine) -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=tools_db_engine)
    Base.metadata.create_all(bind=tools_db_engine)

    session_factory = make_session_factory(tools_db_engine)
    with session_factory() as session:
        seed_database(session)

    yield


@pytest.fixture()
def tools_db_session(
    seeded_tools_db: None, tools_db_engine: Engine
) -> Generator[Session, None, None]:
    session_factory = make_session_factory(tools_db_engine)
    with session_factory() as session:
        yield session


@pytest.fixture()
def tools_client(
    seeded_tools_db: None, tools_db_engine: Engine
) -> Generator[TestClient, None, None]:
    from app.db.dependencies import get_db_session

    session_factory = make_session_factory(tools_db_engine)

    def override_get_db_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
