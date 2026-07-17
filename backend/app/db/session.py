import os
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:123456@localhost:5432/postgres"


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def get_database_url() -> str:
    return normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))


def make_engine(database_url: str | None = None, **kwargs: Any) -> Engine:
    url = normalize_database_url(database_url) if database_url else get_database_url()
    return create_engine(url, pool_pre_ping=True, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
