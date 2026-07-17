from __future__ import annotations

import os

from sqlalchemy import select

from app.db.base import Base
from app.db.session import make_engine, make_session_factory
from app.models import AdminUser
from app.services.admin_auth import create_admin_user, hash_password


def seed_admin_user() -> None:
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    role = os.getenv("ADMIN_ROLE", "admin").strip() or "admin"
    reset_password = os.getenv("ADMIN_RESET_PASSWORD", "").lower() == "true"

    if not username or not password:
        raise RuntimeError("ADMIN_USERNAME and ADMIN_PASSWORD are required.")

    engine = make_engine()
    Base.metadata.create_all(bind=engine)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        admin = session.scalar(select(AdminUser).where(AdminUser.username == username))
        if admin is None:
            create_admin_user(session, username=username, password=password, role=role)
            action = "created"
        elif reset_password:
            password_hash, password_salt = hash_password(password)
            admin.password_hash = password_hash
            admin.password_salt = password_salt
            admin.role = role
            admin.is_active = True
            session.commit()
            action = "updated"
        else:
            action = "already_exists"

    engine.dispose()
    print(f"Admin user {action}: username={username}, role={role}.")


if __name__ == "__main__":
    seed_admin_user()
