from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Ticket


def test_get_order_info_returns_seeded_order(tools_client: TestClient) -> None:
    response = tools_client.get("/api/tools/orders/ORD-2026-0001")

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "get_order_info"
    assert data["order_number"] == "ORD-2026-0001"
    assert data["user"]["external_id"] == "U0001"
    assert data["status"] == "shipped"
    assert len(data["items"]) >= 1
    assert data["items"][0]["sku"].startswith("SKU-")


def test_get_user_profile_returns_seeded_user(tools_client: TestClient) -> None:
    response = tools_client.get("/api/tools/users/U0001")

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "get_user_profile"
    assert data["external_id"] == "U0001"
    assert data["name"] == "Customer 01"
    assert data["total_orders"] > 0
    assert data["total_tickets"] > 0


def test_get_shipment_status_returns_seeded_shipment(tools_client: TestClient) -> None:
    response = tools_client.get("/api/tools/shipments/TRK-2026-0001")

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "get_shipment_status"
    assert data["tracking_number"] == "TRK-2026-0001"
    assert data["order_number"] == "ORD-2026-0001"
    assert data["status"] == "delivered"
    assert data["last_checkpoint"] == "Checkpoint 01"


def test_query_missing_records_returns_clear_errors(tools_client: TestClient) -> None:
    cases = [
        ("/api/tools/orders/ORD-NOT-FOUND", "ORDER_NOT_FOUND"),
        ("/api/tools/users/U-NOT-FOUND", "USER_NOT_FOUND"),
        ("/api/tools/shipments/TRK-NOT-FOUND", "SHIPMENT_NOT_FOUND"),
    ]

    for path, expected_code in cases:
        response = tools_client.get(path)

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == expected_code
        assert "not found" in response.json()["detail"]["message"].lower()


def test_create_ticket_successfully_persists_ticket(tools_client: TestClient) -> None:
    response = tools_client.post(
        "/api/tools/tickets",
        json={
            "order_number": "ORD-2026-0031",
            "external_id": "U0001",
            "category": "refund",
            "priority": "high",
            "subject": "Refund request",
            "description": "Customer asks for a refund after receiving damaged goods.",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["tool_name"] == "create_ticket"
    assert data["ticket_number"].startswith("TCK-2026-")
    assert data["order_number"] == "ORD-2026-0031"
    assert data["external_id"] == "U0001"
    assert data["status"] == "open"


def test_update_ticket_status_successfully_changes_status(
    tools_client: TestClient,
) -> None:
    response = tools_client.patch(
        "/api/tools/tickets/TCK-2026-0001/status",
        json={"status": "resolved", "resolution": "Customer accepted the answer."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "update_ticket_status"
    assert data["ticket_number"] == "TCK-2026-0001"
    assert data["status"] == "resolved"
    assert data["resolution"] == "Customer accepted the answer."


def test_escalate_to_human_only_marks_ticket_as_escalated(
    tools_client: TestClient,
    tools_db_session: Session,
) -> None:
    before = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0004")
    )
    assert before is not None
    original_priority = before.priority
    original_resolution = before.resolution

    response = tools_client.post(
        "/api/tools/tickets/TCK-2026-0004/escalate",
        json={"reason": "Customer requests a human specialist."},
    )

    tools_db_session.expire_all()
    after = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0004")
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "escalate_to_human"
    assert data["handled_by_ai"] is False
    assert data["ticket_number"] == "TCK-2026-0004"
    assert data["status"] == "escalated"
    assert after is not None
    assert after.status == "escalated"
    assert after.priority == original_priority
    assert after.resolution == original_resolution


def test_refund_eligibility_returns_recommendation_without_modifying_order(
    tools_client: TestClient,
    tools_db_session: Session,
) -> None:
    before = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )
    assert before is not None
    original_status = before.status
    original_payment_status = before.payment_status

    response = tools_client.post(
        "/api/tools/refunds/check-eligibility",
        json={"order_number": "ORD-2026-0002", "reason": "Damaged product"},
    )

    tools_db_session.expire_all()
    after = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "check_refund_eligibility"
    assert data["order_number"] == "ORD-2026-0002"
    assert data["eligible"] is True
    assert data["recommendation"] == "approve_review"
    assert data["high_risk_action_executed"] is False
    assert after is not None
    assert after.status == original_status
    assert after.payment_status == original_payment_status


def test_refund_amount_calculation_returns_suggestion_without_modifying_order(
    tools_client: TestClient,
    tools_db_session: Session,
) -> None:
    before = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )
    assert before is not None
    original_total = before.total_amount
    original_status = before.status
    original_payment_status = before.payment_status

    response = tools_client.post(
        "/api/tools/refunds/calculate-amount",
        json={
            "order_number": "ORD-2026-0002",
            "reason": "Damaged product",
            "requested_amount": "50.00",
        },
    )

    tools_db_session.expire_all()
    after = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_name"] == "calculate_refund_amount"
    assert Decimal(str(data["suggested_amount"])) == Decimal("50.00")
    assert Decimal(str(data["max_refundable_amount"])) == original_total
    assert data["high_risk_action_executed"] is False
    assert after is not None
    assert after.total_amount == original_total
    assert after.status == original_status
    assert after.payment_status == original_payment_status
