from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.dependencies import get_db_session
from app.schemas.tickets import (
    TicketDetailResponse,
    TicketListFilters,
    TicketListResponse,
    TicketStatusUpdateRequest,
)
from app.services import tickets as ticket_service
from app.services.tool_errors import ToolError


router = APIRouter(prefix="/api/tickets", tags=["tickets"])
DbSession = Annotated[Session, Depends(get_db_session)]


def _raise_tool_error(error: ToolError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


@router.get("", response_model=TicketListResponse)
def list_tickets(
    session: DbSession,
    status: Annotated[str | None, Query(min_length=1, max_length=32)] = None,
    category: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    priority: Annotated[str | None, Query(min_length=1, max_length=24)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1, le=100)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
) -> TicketListResponse:
    return ticket_service.list_tickets(
        session,
        TicketListFilters(
            status=status,
            category=category,
            priority=priority,
            page=page,
            page_size=page_size or limit or 50,
        ),
    )


@router.get("/{ticket_number}", response_model=TicketDetailResponse)
def get_ticket_detail(ticket_number: str, session: DbSession) -> TicketDetailResponse:
    try:
        return ticket_service.get_ticket_detail(session, ticket_number)
    except ToolError as error:
        _raise_tool_error(error)


@router.patch("/{ticket_number}/status", response_model=TicketDetailResponse)
def update_ticket_status(
    ticket_number: str,
    request: TicketStatusUpdateRequest,
    session: DbSession,
) -> TicketDetailResponse:
    try:
        return ticket_service.update_ticket_status(session, ticket_number, request)
    except ToolError as error:
        _raise_tool_error(error)
