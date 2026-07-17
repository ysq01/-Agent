from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentFeedback(Base):
    __tablename__ = "agent_feedback"
    __table_args__ = (
        CheckConstraint(
            "feedback_type in ('accepted', 'edited', 'rejected')",
            name="ck_agent_feedback_type",
        ),
        CheckConstraint(
            "agent_mode is null or agent_mode in ('rules', 'llm_assisted')",
            name="ck_agent_feedback_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(Text)
    intent: Mapped[str] = mapped_column(String(40), index=True)
    ai_reply: Mapped[str] = mapped_column(Text)
    final_reply: Mapped[str | None] = mapped_column(Text)
    feedback_type: Mapped[str] = mapped_column(String(24), index=True)
    reason: Mapped[str | None] = mapped_column(String(500))
    ticket_number: Mapped[str | None] = mapped_column(String(40), index=True)
    order_number: Mapped[str | None] = mapped_column(String(40), index=True)
    agent_mode: Mapped[str | None] = mapped_column(String(24), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
