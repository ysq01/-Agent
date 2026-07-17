from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models import AgentFeedback
from app.schemas.feedback import (
    AgentFeedbackCreateRequest,
    AgentFeedbackCreateResponse,
    FeedbackRecentItem,
    FeedbackSummaryResponse,
)


RECENT_FEEDBACK_LIMIT = 10
PREVIEW_LENGTH = 80


def create_agent_feedback(
    session: Session, request: AgentFeedbackCreateRequest
) -> AgentFeedbackCreateResponse:
    feedback = AgentFeedback(
        message=request.message,
        intent=request.intent,
        ai_reply=request.ai_reply,
        final_reply=request.final_reply,
        feedback_type=request.feedback_type,
        reason=request.reason,
        ticket_number=request.ticket_number,
        order_number=request.order_number,
        agent_mode=request.agent_mode,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)

    return AgentFeedbackCreateResponse(
        id=feedback.id,
        feedback_type=feedback.feedback_type,  # type: ignore[arg-type]
        created_at=feedback.created_at,
    )


def get_feedback_summary(session: Session) -> FeedbackSummaryResponse:
    total = _count_feedback(session)
    accepted_count = _count_feedback(session, "accepted")
    edited_count = _count_feedback(session, "edited")
    rejected_count = _count_feedback(session, "rejected")

    recent_feedback = list(
        session.scalars(
            select(AgentFeedback)
            .order_by(desc(AgentFeedback.created_at), desc(AgentFeedback.id))
            .limit(RECENT_FEEDBACK_LIMIT)
        )
    )

    return FeedbackSummaryResponse(
        total=total,
        accepted_count=accepted_count,
        edited_count=edited_count,
        rejected_count=rejected_count,
        accepted_rate=_rate(accepted_count, total),
        edited_rate=_rate(edited_count, total),
        rejected_rate=_rate(rejected_count, total),
        reason_counts=_reason_counts(session),
        recent_feedback=[
            FeedbackRecentItem(
                id=feedback.id,
                feedback_type=feedback.feedback_type,  # type: ignore[arg-type]
                reason=feedback.reason,
                message_preview=_preview(feedback.message),
                final_reply_preview=(
                    _preview(feedback.final_reply) if feedback.final_reply else None
                ),
                created_at=feedback.created_at,
            )
            for feedback in recent_feedback
        ],
    )


def _count_feedback(session: Session, feedback_type: str | None = None) -> int:
    statement = select(func.count()).select_from(AgentFeedback)
    if feedback_type is not None:
        statement = statement.where(AgentFeedback.feedback_type == feedback_type)
    return session.scalar(statement) or 0


def _reason_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(AgentFeedback.reason, func.count())
        .where(AgentFeedback.reason.is_not(None))
        .group_by(AgentFeedback.reason)
        .order_by(desc(func.count()), AgentFeedback.reason)
    )
    return {reason: count for reason, count in rows if reason}


def _rate(count: int, total: int) -> float:
    if total == 0:
        return 0.0
    return count / total


def _preview(value: str, max_length: int = PREVIEW_LENGTH) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[:max_length]}..."
