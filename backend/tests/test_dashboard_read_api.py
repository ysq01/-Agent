from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Product, Ticket


def test_list_tickets_returns_seeded_ticket_summaries(
    tools_client: TestClient,
) -> None:
    response = tools_client.get("/api/tickets?limit=5")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 30
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert data["total_pages"] == 6
    assert len(data["tickets"]) == 5

    ticket = data["tickets"][0]
    assert set(ticket) == {
        "ticket_number",
        "order_number",
        "external_id",
        "category",
        "status",
        "priority",
        "handled_by_ai",
        "is_escalated",
        "created_at",
    }
    assert ticket["ticket_number"].startswith("TCK-2026-")
    assert ticket["order_number"].startswith("ORD-2026-")
    assert ticket["external_id"].startswith("U")
    assert isinstance(ticket["handled_by_ai"], bool)
    assert isinstance(ticket["is_escalated"], bool)


def test_list_tickets_supports_pagination(
    tools_client: TestClient,
) -> None:
    first_response = tools_client.get(
        "/api/tickets",
        params={"page": 1, "page_size": 5},
    )
    second_response = tools_client.get(
        "/api/tickets",
        params={"page": 2, "page_size": 5},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    first_page = first_response.json()
    second_page = second_response.json()
    assert first_page["total"] == 30
    assert first_page["page"] == 1
    assert first_page["page_size"] == 5
    assert first_page["total_pages"] == 6
    assert second_page["total"] == 30
    assert second_page["page"] == 2
    assert second_page["page_size"] == 5
    assert second_page["total_pages"] == 6
    assert len(second_page["tickets"]) == 5
    assert {
        ticket["ticket_number"] for ticket in first_page["tickets"]
    }.isdisjoint({ticket["ticket_number"] for ticket in second_page["tickets"]})


def test_list_tickets_supports_simple_filters(
    tools_client: TestClient,
) -> None:
    response = tools_client.get(
        "/api/tickets",
        params={"status": "escalated", "category": "invoice", "priority": "medium"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    for ticket in data["tickets"]:
        assert ticket["status"] == "escalated"
        assert ticket["category"] == "invoice"
        assert ticket["priority"] == "medium"
        assert ticket["handled_by_ai"] is False
        assert ticket["is_escalated"] is True


def test_get_ticket_detail_returns_order_and_customer_fields(
    tools_client: TestClient,
) -> None:
    response = tools_client.get("/api/tickets/TCK-2026-0001")

    assert response.status_code == 200
    data = response.json()
    assert data["ticket_number"] == "TCK-2026-0001"
    assert data["order_number"] == "ORD-2026-0001"
    assert data["external_id"] == "U0001"
    assert data["category"] == "delivery"
    assert data["status"] == "pending"
    assert data["priority"] == "medium"
    assert data["subject"] == "After-sales request for ORD-2026-0001"
    assert data["description"]
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["order_summary"]["payment_status"] == "paid"
    assert data["user_summary"]["name"] == "Customer 01"


def test_get_missing_ticket_returns_404(
    tools_client: TestClient,
) -> None:
    response = tools_client.get("/api/tickets/TCK-2026-9999")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "TICKET_NOT_FOUND"


def test_update_ticket_status_from_ticket_center_persists_resolution_and_keeps_order_data(
    tools_client: TestClient,
    tools_db_session: Session,
) -> None:
    before_ticket = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )
    assert before_ticket is not None
    before_order = before_ticket.order
    original_order_status = before_order.status
    original_payment_status = before_order.payment_status
    original_stock = {
        item.product.sku: item.product.stock_quantity for item in before_order.items
    }

    response = tools_client.patch(
        "/api/tickets/TCK-2026-0001/status",
        json={
            "status": "resolved",
            "resolution": "  已联系客户，售后专员已确认处理完成。  ",
        },
    )

    tools_db_session.expire_all()
    after_ticket = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )
    after_order = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0001")
    )
    stock_after = {
        product.sku: product.stock_quantity
        for product in tools_db_session.scalars(
            select(Product).where(Product.sku.in_(original_stock.keys()))
        )
    }

    assert response.status_code == 200
    data = response.json()
    assert "tool_name" not in data
    assert data["ticket_number"] == "TCK-2026-0001"
    assert data["status"] == "resolved"
    assert data["resolution"] == "已联系客户，售后专员已确认处理完成。"
    assert after_ticket is not None
    assert after_ticket.status == "resolved"
    assert after_ticket.resolution == "已联系客户，售后专员已确认处理完成。"
    assert after_order is not None
    assert after_order.status == original_order_status
    assert after_order.payment_status == original_payment_status
    assert stock_after == original_stock


def test_update_ticket_status_rejects_invalid_status_without_changing_ticket(
    tools_client: TestClient,
    tools_db_session: Session,
) -> None:
    before = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )
    assert before is not None
    original_status = before.status
    original_resolution = before.resolution

    response = tools_client.patch(
        "/api/tickets/TCK-2026-0001/status",
        json={"status": "waiting_for_magic", "resolution": "非法状态不应保存"},
    )

    tools_db_session.expire_all()
    after = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_TICKET_STATUS"
    assert after is not None
    assert after.status == original_status
    assert after.resolution == original_resolution


def test_update_ticket_status_requires_resolution_for_resolved_or_closed(
    tools_client: TestClient,
    tools_db_session: Session,
) -> None:
    response = tools_client.patch(
        "/api/tickets/TCK-2026-0001/status",
        json={"status": "closed", "resolution": "   "},
    )

    tools_db_session.expire_all()
    ticket = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TICKET_RESOLUTION_REQUIRED"
    assert ticket is not None
    assert ticket.status == "pending"
    assert ticket.resolution is None


def test_update_ticket_status_allows_non_final_status_without_resolution(
    tools_client: TestClient,
) -> None:
    response = tools_client.patch(
        "/api/tickets/TCK-2026-0001/status",
        json={"status": "escalated"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ticket_number"] == "TCK-2026-0001"
    assert data["status"] == "escalated"
    assert data["resolution"] is None


def test_list_knowledge_documents_reads_local_policy_files(
    tools_client: TestClient,
) -> None:
    response = tools_client.get("/api/knowledge/documents")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 7
    assert len(data["documents"]) == data["total"]

    document = data["documents"][0]
    assert set(document) == {
        "policy_title",
        "source_file",
        "character_count",
        "preview",
        "content",
    }
    assert document["source_file"].endswith((".md", ".txt"))
    assert document["character_count"] > 0
    assert 0 < len(document["preview"]) <= 160
    assert len(document["content"]) == document["character_count"]
    assert document["preview"] in " ".join(document["content"].split())

    titles = {item["policy_title"] for item in data["documents"]}
    assert "七天无理由退货规则" in titles


def test_local_frontend_origin_is_allowed_for_api_demo(
    tools_client: TestClient,
) -> None:
    response = tools_client.options(
        "/api/tickets",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
