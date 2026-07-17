from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.admin import AdminUser


class PolicyDocument(Base):
    __tablename__ = "policy_documents"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'published', 'disabled')",
            name="ck_policy_documents_status",
        ),
        CheckConstraint(
            "source in ('admin', 'file_seed')",
            name="ck_policy_documents_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(24), default="admin", index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("admin_users.id"),
        index=True,
    )
    supersedes_policy_id: Mapped[int | None] = mapped_column(
        ForeignKey("policy_documents.id"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator: Mapped["AdminUser | None"] = relationship(back_populates="policies")
