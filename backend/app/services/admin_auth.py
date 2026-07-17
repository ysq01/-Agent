from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdminSession, AdminUser


PASSWORD_HASH_ITERATIONS = 260_000
ADMIN_SESSION_HOURS = 24


@dataclass(frozen=True)
class AdminSessionLogin:
    token: str
    role: str
    expires_at: datetime


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    password_hash = _pbkdf2_hash(password, salt)
    return password_hash, salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    candidate = _pbkdf2_hash(password, password_salt)
    return hmac.compare_digest(candidate, password_hash)


def create_admin_user(
    session: Session,
    username: str,
    password: str,
    role: str = "admin",
) -> AdminUser:
    password_hash, password_salt = hash_password(password)
    admin = AdminUser(
        username=username.strip(),
        password_hash=password_hash,
        password_salt=password_salt,
        role=role,
        is_active=True,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin


def authenticate_admin(
    session: Session,
    username: str,
    password: str,
) -> AdminSessionLogin | None:
    admin = session.scalar(
        select(AdminUser).where(AdminUser.username == username.strip())
    )
    if admin is None or not admin.is_active:
        return None
    if not verify_password(password, admin.password_hash, admin.password_salt):
        return None

    token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(hours=ADMIN_SESSION_HOURS)
    session_record = AdminSession(
        token_hash=hash_token(token),
        admin_user=admin,
        expires_at=expires_at,
    )
    session.add(session_record)
    session.commit()

    return AdminSessionLogin(token=token, role=admin.role, expires_at=expires_at)


def get_admin_by_token(session: Session, token: str) -> AdminUser | None:
    now = _utcnow()
    return session.scalar(
        select(AdminUser)
        .join(AdminSession)
        .where(
            AdminSession.token_hash == hash_token(token),
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > now,
            AdminUser.is_active.is_(True),
        )
    )


def revoke_admin_session(session: Session, token: str) -> bool:
    session_record = session.scalar(
        select(AdminSession).where(
            AdminSession.token_hash == hash_token(token),
            AdminSession.revoked_at.is_(None),
        )
    )
    if session_record is None:
        return False

    session_record.revoked_at = _utcnow()
    session.commit()
    return True


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _pbkdf2_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        _password_hash_iterations(),
    ).hex()


def _password_hash_iterations() -> int:
    configured = os.getenv("ADMIN_PASSWORD_HASH_ITERATIONS")
    if configured and configured.isdigit():
        return int(configured)
    return PASSWORD_HASH_ITERATIONS


def _utcnow() -> datetime:
    return datetime.now(UTC)
