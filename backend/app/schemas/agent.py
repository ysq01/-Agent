from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgentIntent = Literal[
    "refund_request",
    "shipping_issue",
    "invoice_request",
    "account_issue",
    "complaint",
    "other",
]

AgentMode = Literal["rules", "llm_assisted"]

AgentActionStatus = Literal["success", "skipped", "failed"]


class AgentSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class AgentProcessRequest(AgentSchema):
    message: str = Field(min_length=1)
    order_number: str | None = None
    external_id: str | None = None
    ticket_number: str | None = None
    requested_amount: Decimal | None = Field(default=None, gt=0)
    mode: AgentMode | None = None


class AgentAction(AgentSchema):
    node: str
    tool_name: str | None = None
    status: AgentActionStatus
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentPolicySource(AgentSchema):
    policy_title: str
    source_file: str
    score: float


class AgentProcessResponse(AgentSchema):
    intent: AgentIntent
    reply: str
    actions: list[AgentAction]
    policy_sources: list[AgentPolicySource]
    need_human: bool
    ticket_id: str | None
    confidence: float = Field(ge=0, le=1)
