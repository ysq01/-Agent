from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.agent import AgentIntent, AgentMode


FeedbackType = Literal["accepted", "edited", "rejected"]


class FeedbackSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class AgentFeedbackCreateRequest(FeedbackSchema):
    message: str = Field(min_length=1)
    intent: AgentIntent
    ai_reply: str = Field(min_length=1)
    final_reply: str | None = Field(default=None, max_length=2000)
    feedback_type: FeedbackType
    reason: str | None = Field(default=None, max_length=500)
    ticket_number: str | None = Field(default=None, max_length=40)
    order_number: str | None = Field(default=None, max_length=40)
    agent_mode: AgentMode | None = None

    @field_validator("final_reply", "reason", "ticket_number", "order_number", mode="after")
    @classmethod
    def empty_string_to_none(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def validate_feedback_requirements(self) -> "AgentFeedbackCreateRequest":
        if self.feedback_type == "edited" and not self.final_reply:
            raise ValueError("final_reply is required when feedback_type is edited")
        if self.feedback_type == "rejected" and not self.reason:
            raise ValueError("reason is required when feedback_type is rejected")
        return self


class AgentFeedbackCreateResponse(FeedbackSchema):
    id: int
    feedback_type: FeedbackType
    created_at: datetime


class FeedbackRecentItem(FeedbackSchema):
    id: int
    feedback_type: FeedbackType
    reason: str | None
    message_preview: str
    final_reply_preview: str | None
    created_at: datetime


class FeedbackSummaryResponse(FeedbackSchema):
    total: int
    accepted_count: int
    edited_count: int
    rejected_count: int
    accepted_rate: float
    edited_rate: float
    rejected_rate: float
    reason_counts: dict[str, int]
    recent_feedback: list[FeedbackRecentItem]
