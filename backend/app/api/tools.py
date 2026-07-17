from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.dependencies import get_db_session
from app.schemas.tools import (
    CreateTicketRequest,
    EscalateTicketRequest,
    EscalateTicketResponse,
    RefundAmountRequest,
    RefundAmountResponse,
    RefundEligibilityRequest,
    RefundEligibilityResponse,
    PolicySearchRequest,
    PolicySearchResponse,
    PolicySearchResult,
    ShipmentStatusResponse,
    TicketResponse,
    UpdateTicketStatusRequest,
    UserProfileResponse,
    OrderInfoResponse,
)
from app.services import policy_knowledge
from app.services import tools as tool_service
from app.services.tool_errors import ToolError


router = APIRouter(prefix="/api/tools", tags=["tools"])
DbSession = Annotated[Session, Depends(get_db_session)]


def _raise_tool_error(error: ToolError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code, "message": error.message},
    )


@router.get("/orders/{order_number}", response_model=OrderInfoResponse)
def get_order_info(order_number: str, session: DbSession) -> OrderInfoResponse:
    try:
        return tool_service.get_order_info(session, order_number)
    except ToolError as error:
        _raise_tool_error(error)


@router.get("/users/{external_id}", response_model=UserProfileResponse)
def get_user_profile(external_id: str, session: DbSession) -> UserProfileResponse:
    try:
        return tool_service.get_user_profile(session, external_id)
    except ToolError as error:
        _raise_tool_error(error)


@router.get("/shipments/{tracking_number}", response_model=ShipmentStatusResponse)
def get_shipment_status(
    tracking_number: str, session: DbSession
) -> ShipmentStatusResponse:
    try:
        return tool_service.get_shipment_status(session, tracking_number)
    except ToolError as error:
        _raise_tool_error(error)


@router.post(
    "/refunds/check-eligibility",
    response_model=RefundEligibilityResponse,
)
def check_refund_eligibility(
    request: RefundEligibilityRequest, session: DbSession
) -> RefundEligibilityResponse:
    try:
        return tool_service.check_refund_eligibility(session, request)
    except ToolError as error:
        _raise_tool_error(error)


@router.post("/refunds/calculate-amount", response_model=RefundAmountResponse)
def calculate_refund_amount(
    request: RefundAmountRequest, session: DbSession
) -> RefundAmountResponse:
    try:
        return tool_service.calculate_refund_amount(session, request)
    except ToolError as error:
        _raise_tool_error(error)


@router.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(request: CreateTicketRequest, session: DbSession) -> TicketResponse:
    try:
        return tool_service.create_ticket(session, request)
    except ToolError as error:
        _raise_tool_error(error)


@router.patch("/tickets/{ticket_number}/status", response_model=TicketResponse)
def update_ticket_status(
    ticket_number: str, request: UpdateTicketStatusRequest, session: DbSession
) -> TicketResponse:
    try:
        return tool_service.update_ticket_status(session, ticket_number, request)
    except ToolError as error:
        _raise_tool_error(error)


@router.post(
    "/tickets/{ticket_number}/escalate",
    response_model=EscalateTicketResponse,
)
def escalate_to_human(
    ticket_number: str, request: EscalateTicketRequest, session: DbSession
) -> EscalateTicketResponse:
    try:
        return tool_service.escalate_to_human(session, ticket_number, request)
    except ToolError as error:
        _raise_tool_error(error)


@router.post("/policies/search", response_model=PolicySearchResponse)
def search_policy(request: PolicySearchRequest, session: DbSession) -> PolicySearchResponse:
    matches = policy_knowledge.search_policy(
        query=request.query,
        top_k=request.top_k,
        session=session,
    )
    return PolicySearchResponse(
        query=request.query,
        results=[
            PolicySearchResult(
                policy_title=match.policy_title,
                matched_text=match.matched_text,
                score=match.score,
                source_file=match.source_file,
            )
            for match in matches
        ],
    )
