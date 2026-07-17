from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Order, OrderItem, Shipment, Ticket, User
from app.schemas.tools import (
    CreateTicketRequest,
    EscalateTicketRequest,
    EscalateTicketResponse,
    OrderInfoResponse,
    OrderItemSummary,
    OrderShipmentSummary,
    OrderUserSummary,
    RefundAmountRequest,
    RefundAmountResponse,
    RefundEligibilityRequest,
    RefundEligibilityResponse,
    ShipmentStatusResponse,
    TicketResponse,
    UpdateTicketStatusRequest,
    UserProfileResponse,
)
from app.services.tool_errors import ToolNotFoundError, ToolValidationError


ALLOWED_TICKET_STATUSES = {"open", "pending", "escalated", "resolved", "closed"}
MONEY_QUANT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _get_order(session: Session, order_number: str) -> Order:
    statement = (
        select(Order)
        .options(
            joinedload(Order.user),
            selectinload(Order.items).joinedload(OrderItem.product),
            selectinload(Order.shipments),
        )
        .where(Order.order_number == order_number)
    )
    order = session.execute(statement).scalar_one_or_none()
    if order is None:
        raise ToolNotFoundError(
            code="ORDER_NOT_FOUND",
            message=f"Order {order_number} was not found.",
        )
    return order


def _get_user(session: Session, external_id: str) -> User:
    statement = (
        select(User)
        .options(selectinload(User.orders), selectinload(User.tickets))
        .where(User.external_id == external_id)
    )
    user = session.execute(statement).scalar_one_or_none()
    if user is None:
        raise ToolNotFoundError(
            code="USER_NOT_FOUND",
            message=f"User {external_id} was not found.",
        )
    return user


def _get_shipment(session: Session, tracking_number: str) -> Shipment:
    statement = (
        select(Shipment)
        .options(joinedload(Shipment.order))
        .where(Shipment.tracking_number == tracking_number)
    )
    shipment = session.execute(statement).scalar_one_or_none()
    if shipment is None:
        raise ToolNotFoundError(
            code="SHIPMENT_NOT_FOUND",
            message=f"Shipment {tracking_number} was not found.",
        )
    return shipment


def _get_ticket(session: Session, ticket_number: str) -> Ticket:
    statement = (
        select(Ticket)
        .options(joinedload(Ticket.order), joinedload(Ticket.user))
        .where(Ticket.ticket_number == ticket_number)
    )
    ticket = session.execute(statement).scalar_one_or_none()
    if ticket is None:
        raise ToolNotFoundError(
            code="TICKET_NOT_FOUND",
            message=f"Ticket {ticket_number} was not found.",
        )
    return ticket


def _ticket_response(tool_name: str, ticket: Ticket) -> TicketResponse:
    return TicketResponse(
        tool_name=tool_name,
        ticket_number=ticket.ticket_number,
        order_number=ticket.order.order_number,
        external_id=ticket.user.external_id,
        category=ticket.category,
        status=ticket.status,
        priority=ticket.priority,
        subject=ticket.subject,
        description=ticket.description,
        resolution=ticket.resolution,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _ticket_year_from_order(order_number: str) -> str:
    parts = order_number.split("-")
    if len(parts) >= 3 and parts[1].isdigit():
        return parts[1]
    return "2026"


def _next_ticket_number(session: Session, order_number: str) -> str:
    prefix = f"TCK-{_ticket_year_from_order(order_number)}-"
    existing_numbers = session.scalars(
        select(Ticket.ticket_number).where(Ticket.ticket_number.like(f"{prefix}%"))
    )

    max_suffix = 0
    for ticket_number in existing_numbers:
        suffix = ticket_number.removeprefix(prefix)
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))

    return f"{prefix}{max_suffix + 1:04d}"


def get_order_info(session: Session, order_number: str) -> OrderInfoResponse:
    order = _get_order(session, order_number)

    return OrderInfoResponse(
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        total_amount=_money(order.total_amount),
        placed_at=order.placed_at,
        user=OrderUserSummary(
            external_id=order.user.external_id,
            name=order.user.name,
            tier=order.user.tier,
        ),
        items=[
            OrderItemSummary(
                sku=item.product.sku,
                name=item.product.name,
                quantity=item.quantity,
                unit_price=_money(item.unit_price),
                subtotal=_money(item.subtotal),
            )
            for item in order.items
        ],
        shipments=[
            OrderShipmentSummary(
                tracking_number=shipment.tracking_number,
                carrier=shipment.carrier,
                status=shipment.status,
                last_checkpoint=shipment.last_checkpoint,
            )
            for shipment in order.shipments
        ],
    )


def get_user_profile(session: Session, external_id: str) -> UserProfileResponse:
    user = _get_user(session, external_id)

    return UserProfileResponse(
        external_id=user.external_id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        tier=user.tier,
        total_orders=len(user.orders),
        total_tickets=len(user.tickets),
        created_at=user.created_at,
    )


def get_shipment_status(
    session: Session, tracking_number: str
) -> ShipmentStatusResponse:
    shipment = _get_shipment(session, tracking_number)

    return ShipmentStatusResponse(
        tracking_number=shipment.tracking_number,
        order_number=shipment.order.order_number,
        carrier=shipment.carrier,
        status=shipment.status,
        shipped_at=shipment.shipped_at,
        delivered_at=shipment.delivered_at,
        last_checkpoint=shipment.last_checkpoint,
    )


def check_refund_eligibility(
    session: Session, request: RefundEligibilityRequest
) -> RefundEligibilityResponse:
    order = _get_order(session, request.order_number)
    reasons: list[str] = []

    if order.payment_status != "paid":
        reasons.append(f"Payment status is {order.payment_status}, not paid.")

    if order.status in {"refunding", "cancelled"}:
        reasons.append(f"Order status is already {order.status}.")

    if request.requested_amount is not None and request.requested_amount > order.total_amount:
        reasons.append("Requested refund amount exceeds the order total.")

    eligible = not reasons and order.status in {"paid", "shipped", "delivered", "completed"}
    if eligible:
        recommendation = "approve_review"
        reasons.append("Order is paid and within a refundable status.")
    elif order.payment_status == "refund_pending" or order.status == "refunding":
        recommendation = "manual_review"
    else:
        recommendation = "reject"

    return RefundEligibilityResponse(
        order_number=order.order_number,
        eligible=eligible,
        recommendation=recommendation,
        reasons=reasons,
        max_refundable_amount=_money(order.total_amount),
    )


def calculate_refund_amount(
    session: Session, request: RefundAmountRequest
) -> RefundAmountResponse:
    order = _get_order(session, request.order_number)
    max_refundable_amount = _money(order.total_amount)

    if request.requested_amount is not None:
        suggested_amount = min(_money(request.requested_amount), max_refundable_amount)
        basis = "Requested amount capped at the order total."
    elif order.status in {"delivered", "completed"}:
        suggested_amount = max_refundable_amount
        basis = "Delivered or completed orders default to full refund review."
    elif order.status == "shipped":
        suggested_amount = _money(max_refundable_amount * Decimal("0.80"))
        basis = "Shipped orders default to an 80% refund suggestion pending review."
    else:
        suggested_amount = max_refundable_amount
        basis = "Order status allows refund review up to the paid total."

    return RefundAmountResponse(
        order_number=order.order_number,
        suggested_amount=suggested_amount,
        max_refundable_amount=max_refundable_amount,
        reason=request.reason,
        calculation_basis=basis,
    )


def create_ticket(session: Session, request: CreateTicketRequest) -> TicketResponse:
    order = _get_order(session, request.order_number)
    user = _get_user(session, request.external_id)

    if order.user_id != user.id:
        raise ToolValidationError(
            code="ORDER_USER_MISMATCH",
            message=(
                f"Order {request.order_number} does not belong to user "
                f"{request.external_id}."
            ),
        )

    ticket = Ticket(
        ticket_number=_next_ticket_number(session, order.order_number),
        order=order,
        user=user,
        category=request.category,
        status="open",
        priority=request.priority,
        subject=request.subject,
        description=request.description,
        resolution=None,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    return _ticket_response("create_ticket", ticket)


def update_ticket_status(
    session: Session, ticket_number: str, request: UpdateTicketStatusRequest
) -> TicketResponse:
    ticket = _get_ticket(session, ticket_number)

    if request.status not in ALLOWED_TICKET_STATUSES:
        raise ToolValidationError(
            code="INVALID_TICKET_STATUS",
            message=(
                f"Ticket status {request.status} is invalid. Allowed values: "
                f"{', '.join(sorted(ALLOWED_TICKET_STATUSES))}."
            ),
        )

    ticket.status = request.status
    if request.resolution is not None:
        ticket.resolution = request.resolution

    session.commit()
    session.refresh(ticket)

    return _ticket_response("update_ticket_status", ticket)


def escalate_to_human(
    session: Session, ticket_number: str, request: EscalateTicketRequest
) -> EscalateTicketResponse:
    ticket = _get_ticket(session, ticket_number)
    ticket.status = "escalated"

    session.commit()
    session.refresh(ticket)

    base = _ticket_response("escalate_to_human", ticket)
    return EscalateTicketResponse(
        **base.model_dump(),
        escalation_reason=request.reason,
    )
