from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TicketReadSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class TicketListItem(TicketReadSchema):
    ticket_number: str
    order_number: str
    external_id: str
    category: str
    status: str
    priority: str
    handled_by_ai: bool
    is_escalated: bool
    created_at: datetime | None


class TicketListResponse(TicketReadSchema):
    total: int
    page: int
    page_size: int
    total_pages: int
    tickets: list[TicketListItem]


class TicketOrderSummary(TicketReadSchema):
    order_number: str
    status: str
    payment_status: str
    total_amount: Decimal
    placed_at: datetime


class TicketUserSummary(TicketReadSchema):
    external_id: str
    name: str
    tier: str


class TicketDetailResponse(TicketListItem):
    subject: str
    description: str
    resolution: str | None
    updated_at: datetime | None
    order_summary: TicketOrderSummary
    user_summary: TicketUserSummary


class TicketStatusUpdateRequest(TicketReadSchema):
    status: str = Field(min_length=1, max_length=32)
    resolution: str | None = Field(default=None, max_length=1000)


class TicketListFilters(TicketReadSchema):
    status: str | None = Field(default=None, min_length=1, max_length=32)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    priority: str | None = Field(default=None, min_length=1, max_length=24)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
