import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import Ticket
from app.schemas.tickets import (
    TicketDetailResponse,
    TicketListFilters,
    TicketListItem,
    TicketListResponse,
    TicketOrderSummary,
    TicketStatusUpdateRequest,
    TicketUserSummary,
)
from app.services.tool_errors import ToolNotFoundError, ToolValidationError


ALLOWED_TICKET_STATUSES = {"open", "pending", "escalated", "resolved", "closed"}
FINAL_TICKET_STATUSES = {"resolved", "closed"}


def list_tickets(session: Session, filters: TicketListFilters) -> TicketListResponse:
    count_statement = _apply_ticket_filters(
        select(func.count()).select_from(Ticket),
        filters,
    )
    total = session.scalar(count_statement) or 0
    total_pages = max(1, math.ceil(total / filters.page_size))
    current_page = min(filters.page, total_pages)

    statement = _apply_ticket_filters(
        select(Ticket)
        .options(joinedload(Ticket.order), joinedload(Ticket.user)),
        filters,
    )
    statement = (
        statement.order_by(Ticket.created_at.desc(), Ticket.ticket_number.desc())
        .offset((current_page - 1) * filters.page_size)
        .limit(filters.page_size)
    )

    tickets = list(session.scalars(statement))
    return TicketListResponse(
        total=total,
        page=current_page,
        page_size=filters.page_size,
        total_pages=total_pages,
        tickets=[_ticket_list_item(ticket) for ticket in tickets],
    )


def _apply_ticket_filters(statement, filters: TicketListFilters):
    if filters.status is not None:
        statement = statement.where(Ticket.status == filters.status)
    if filters.category is not None:
        statement = statement.where(Ticket.category == filters.category)
    if filters.priority is not None:
        statement = statement.where(Ticket.priority == filters.priority)
    return statement


def get_ticket_detail(session: Session, ticket_number: str) -> TicketDetailResponse:
    statement = (
        select(Ticket)
        .options(joinedload(Ticket.order), joinedload(Ticket.user))
        .where(Ticket.ticket_number == ticket_number)
    )
    ticket = session.scalar(statement)
    if ticket is None:
        raise ToolNotFoundError(
            code="TICKET_NOT_FOUND",
            message=f"Ticket {ticket_number} was not found.",
        )

    return TicketDetailResponse(
        **_ticket_list_item(ticket).model_dump(),
        subject=ticket.subject,
        description=ticket.description,
        resolution=ticket.resolution,
        updated_at=ticket.updated_at,
        order_summary=TicketOrderSummary(
            order_number=ticket.order.order_number,
            status=ticket.order.status,
            payment_status=ticket.order.payment_status,
            total_amount=ticket.order.total_amount,
            placed_at=ticket.order.placed_at,
        ),
        user_summary=TicketUserSummary(
            external_id=ticket.user.external_id,
            name=ticket.user.name,
            tier=ticket.user.tier,
        ),
    )


def update_ticket_status(
    session: Session, ticket_number: str, request: TicketStatusUpdateRequest
) -> TicketDetailResponse:
    statement = select(Ticket).where(Ticket.ticket_number == ticket_number)
    ticket = session.scalar(statement)
    if ticket is None:
        raise ToolNotFoundError(
            code="TICKET_NOT_FOUND",
            message=f"Ticket {ticket_number} was not found.",
        )

    if request.status not in ALLOWED_TICKET_STATUSES:
        raise ToolValidationError(
            code="INVALID_TICKET_STATUS",
            message=(
                f"Ticket status {request.status} is invalid. Allowed values: "
                f"{', '.join(sorted(ALLOWED_TICKET_STATUSES))}."
            ),
        )

    normalized_resolution = (
        request.resolution.strip() if request.resolution is not None else None
    )
    if request.status in FINAL_TICKET_STATUSES and not normalized_resolution:
        raise ToolValidationError(
            code="TICKET_RESOLUTION_REQUIRED",
            message="Resolution is required when resolving or closing a ticket.",
        )

    ticket.status = request.status
    if request.resolution is not None:
        ticket.resolution = normalized_resolution or None

    session.commit()

    return get_ticket_detail(session, ticket_number)


def _ticket_list_item(ticket: Ticket) -> TicketListItem:
    is_escalated = ticket.status == "escalated"
    return TicketListItem(
        ticket_number=ticket.ticket_number,
        order_number=ticket.order.order_number,
        external_id=ticket.user.external_id,
        category=ticket.category,
        status=ticket.status,
        priority=ticket.priority,
        handled_by_ai=not is_escalated,
        is_escalated=is_escalated,
        created_at=ticket.created_at,
    )
