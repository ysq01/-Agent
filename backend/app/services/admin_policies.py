from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import AdminUser, PolicyDocument
from app.schemas.admin import AdminPolicyCreateRequest, AdminPolicyUpdateRequest
from app.services.policy_knowledge import rebuild_knowledge_base


class AdminPolicyError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def list_admin_policies(
    session: Session,
    status: str | None = None,
) -> list[PolicyDocument]:
    statement = select(PolicyDocument)
    if status:
        statement = statement.where(PolicyDocument.status == status)
    return list(
        session.scalars(
            statement.order_by(desc(PolicyDocument.updated_at), desc(PolicyDocument.id))
        )
    )


def create_policy(
    session: Session,
    request: AdminPolicyCreateRequest,
    admin: AdminUser,
) -> PolicyDocument:
    policy = PolicyDocument(
        title=request.title,
        content=request.content,
        status="draft",
        version=1,
        source="admin",
        content_hash=_content_hash(request.content),
        created_by=admin.id,
    )
    session.add(policy)
    session.commit()
    session.refresh(policy)
    return policy


def update_policy(
    session: Session,
    policy_id: int,
    request: AdminPolicyUpdateRequest,
    admin: AdminUser,
) -> PolicyDocument:
    policy = _get_policy(session, policy_id)
    next_title = request.title if request.title is not None else policy.title
    next_content = request.content if request.content is not None else policy.content

    if policy.status == "published":
        replacement = PolicyDocument(
            title=next_title,
            content=next_content,
            status="draft",
            version=policy.version + 1,
            source="admin",
            content_hash=_content_hash(next_content),
            created_by=admin.id,
            supersedes_policy_id=policy.id,
        )
        session.add(replacement)
        session.commit()
        session.refresh(replacement)
        return replacement

    policy.title = next_title
    policy.content = next_content
    policy.content_hash = _content_hash(next_content)
    session.commit()
    session.refresh(policy)
    return policy


def publish_policy(
    session: Session,
    policy_id: int,
    admin: AdminUser,
) -> PolicyDocument:
    del admin
    policy = _get_policy(session, policy_id)
    now = _utcnow()
    if policy.supersedes_policy_id is not None:
        superseded = session.get(PolicyDocument, policy.supersedes_policy_id)
        if superseded is not None and superseded.status == "published":
            superseded.status = "disabled"
            superseded.disabled_at = now

    policy.status = "published"
    policy.published_at = now
    policy.disabled_at = None
    _rebuild_or_rollback(session)
    session.commit()
    session.refresh(policy)
    return policy


def disable_policy(
    session: Session,
    policy_id: int,
    admin: AdminUser,
) -> PolicyDocument:
    del admin
    policy = _get_policy(session, policy_id)
    policy.status = "disabled"
    policy.disabled_at = _utcnow()
    _rebuild_or_rollback(session)
    session.commit()
    session.refresh(policy)
    return policy


def _get_policy(session: Session, policy_id: int) -> PolicyDocument:
    policy = session.get(PolicyDocument, policy_id)
    if policy is None:
        raise AdminPolicyError("政策不存在。", status_code=404)
    return policy


def _rebuild_or_rollback(session: Session) -> None:
    session.flush()
    try:
        rebuild_knowledge_base(session)
    except Exception as error:
        session.rollback()
        raise AdminPolicyError(
            "知识库更新失败，请确认向量服务已启动后重试。",
            status_code=503,
        ) from error


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(UTC)
