from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ErrorDetail(ToolSchema):
    code: str
    message: str


class OrderUserSummary(ToolSchema):
    external_id: str
    name: str
    tier: str


class OrderItemSummary(ToolSchema):
    sku: str
    name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class OrderShipmentSummary(ToolSchema):
    tracking_number: str
    carrier: str
    status: str
    last_checkpoint: str


class OrderInfoResponse(ToolSchema):
    tool_name: Literal["get_order_info"] = "get_order_info"
    order_number: str
    status: str
    payment_status: str
    total_amount: Decimal
    placed_at: datetime
    user: OrderUserSummary
    items: list[OrderItemSummary]
    shipments: list[OrderShipmentSummary]


class UserProfileResponse(ToolSchema):
    tool_name: Literal["get_user_profile"] = "get_user_profile"
    external_id: str
    name: str
    email: str
    phone: str
    tier: str
    total_orders: int
    total_tickets: int
    created_at: datetime


class ShipmentStatusResponse(ToolSchema):
    tool_name: Literal["get_shipment_status"] = "get_shipment_status"
    tracking_number: str
    order_number: str
    carrier: str
    status: str
    shipped_at: datetime | None
    delivered_at: datetime | None
    last_checkpoint: str


class RefundEligibilityRequest(ToolSchema):
    order_number: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_amount: Decimal | None = Field(default=None, gt=0)


class RefundEligibilityResponse(ToolSchema):
    tool_name: Literal["check_refund_eligibility"] = "check_refund_eligibility"
    order_number: str
    eligible: bool
    recommendation: Literal["approve_review", "manual_review", "reject"]
    reasons: list[str]
    max_refundable_amount: Decimal
    high_risk_action_executed: Literal[False] = False


class RefundAmountRequest(ToolSchema):
    order_number: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_amount: Decimal | None = Field(default=None, gt=0)


class RefundAmountResponse(ToolSchema):
    tool_name: Literal["calculate_refund_amount"] = "calculate_refund_amount"
    order_number: str
    suggested_amount: Decimal
    max_refundable_amount: Decimal
    reason: str
    calculation_basis: str
    high_risk_action_executed: Literal[False] = False


class CreateTicketRequest(ToolSchema):
    order_number: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=40)
    priority: str = Field(default="medium", min_length=1, max_length=24)
    subject: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1)


class UpdateTicketStatusRequest(ToolSchema):
    status: str = Field(min_length=1, max_length=32)
    resolution: str | None = None


class EscalateTicketRequest(ToolSchema):
    reason: str = Field(min_length=1)


class TicketResponse(ToolSchema):
    tool_name: str
    ticket_number: str
    order_number: str
    external_id: str
    category: str
    status: str
    priority: str
    subject: str
    description: str
    resolution: str | None
    created_at: datetime | None
    updated_at: datetime | None


class EscalateTicketResponse(TicketResponse):
    tool_name: Literal["escalate_to_human"] = "escalate_to_human"
    handled_by_ai: Literal[False] = False
    escalation_reason: str


class PolicySearchRequest(ToolSchema):
    query: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)


class PolicySearchResult(ToolSchema):
    policy_title: str
    matched_text: str
    score: float
    source_file: str


class PolicySearchResponse(ToolSchema):
    tool_name: Literal["search_policy"] = "search_policy"
    query: str
    results: list[PolicySearchResult]
