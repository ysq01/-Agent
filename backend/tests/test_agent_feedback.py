from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Product, Ticket


def _feedback_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "message": "ORD-2026-0002 商品破损，我想申请退款",
        "intent": "refund_request",
        "ai_reply": "已核对订单和售后政策，建议进入退款审核。",
        "feedback_type": "accepted",
        "ticket_number": "TCK-2026-0001",
        "order_number": "ORD-2026-0002",
        "agent_mode": "rules",
    }
    payload.update(overrides)
    return payload


def test_create_accepted_feedback(tools_client: TestClient) -> None:
    response = tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] > 0
    assert data["feedback_type"] == "accepted"
    assert data["created_at"]


def test_create_edited_feedback_requires_final_reply(
    tools_client: TestClient,
) -> None:
    missing_response = tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(feedback_type="edited"),
    )

    assert missing_response.status_code == 422

    response = tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(
            feedback_type="edited",
            final_reply="您好，商品破损问题已记录，建议先保留照片并提交售后审核。",
            reason="补充了凭证提醒",
        ),
    )

    assert response.status_code == 201
    assert response.json()["feedback_type"] == "edited"


def test_create_rejected_feedback_requires_reason(tools_client: TestClient) -> None:
    missing_response = tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(feedback_type="rejected"),
    )

    assert missing_response.status_code == 422

    response = tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(
            feedback_type="rejected",
            reason="没有识别出客户要求人工介入",
            final_reply="我会为您转接售后专员继续处理。",
        ),
    )

    assert response.status_code == 201
    assert response.json()["feedback_type"] == "rejected"


def test_rejects_invalid_feedback_type(tools_client: TestClient) -> None:
    response = tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(feedback_type="maybe"),
    )

    assert response.status_code == 422


def test_feedback_summary_returns_zero_state(tools_client: TestClient) -> None:
    response = tools_client.get("/api/eval/feedback-summary")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "total": 0,
        "accepted_count": 0,
        "edited_count": 0,
        "rejected_count": 0,
        "accepted_rate": 0.0,
        "edited_rate": 0.0,
        "rejected_rate": 0.0,
        "reason_counts": {},
        "recent_feedback": [],
    }


def test_feedback_summary_calculates_rates_reasons_and_recent_samples(
    tools_client: TestClient,
) -> None:
    tools_client.post("/api/agent/feedback", json=_feedback_payload())
    tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(
            feedback_type="edited",
            final_reply="您好，已为您补充售后凭证说明。",
            reason="  补充凭证说明  ",
        ),
    )
    tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(
            message="我要投诉，没人处理我的物流问题",
            intent="complaint",
            ai_reply="建议查询物流状态。",
            feedback_type="rejected",
            reason="没有升级人工",
            final_reply="我会为您转接售后主管继续跟进。",
            ticket_number="TCK-2026-0004",
            order_number="ORD-2026-0004",
        ),
    )

    response = tools_client.get("/api/eval/feedback-summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["accepted_count"] == 1
    assert data["edited_count"] == 1
    assert data["rejected_count"] == 1
    assert data["accepted_rate"] == 1 / 3
    assert data["edited_rate"] == 1 / 3
    assert data["rejected_rate"] == 1 / 3
    assert data["reason_counts"] == {
        "补充凭证说明": 1,
        "没有升级人工": 1,
    }
    assert len(data["recent_feedback"]) == 3
    assert data["recent_feedback"][0]["feedback_type"] == "rejected"
    assert data["recent_feedback"][0]["reason"] == "没有升级人工"
    assert data["recent_feedback"][0]["message_preview"] == "我要投诉，没人处理我的物流问题"
    assert data["recent_feedback"][0]["final_reply_preview"] == (
        "我会为您转接售后主管继续跟进。"
    )


def test_feedback_creation_does_not_modify_business_state(
    tools_client: TestClient,
    tools_db_session: Session,
) -> None:
    order_before = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )
    ticket_before = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )
    product_before = tools_db_session.scalar(select(Product).where(Product.sku == "SKU-0001"))
    assert order_before is not None
    assert ticket_before is not None
    assert product_before is not None
    original_order_status = order_before.status
    original_payment_status = order_before.payment_status
    original_ticket_status = ticket_before.status
    original_stock = product_before.stock_quantity

    response = tools_client.post(
        "/api/agent/feedback",
        json=_feedback_payload(
            feedback_type="rejected",
            reason="需要人工复核后处理",
            final_reply="我会为您转接人工专员。",
        ),
    )

    tools_db_session.expire_all()
    order_after = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )
    ticket_after = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )
    product_after = tools_db_session.scalar(select(Product).where(Product.sku == "SKU-0001"))

    assert response.status_code == 201
    assert order_after is not None
    assert ticket_after is not None
    assert product_after is not None
    assert order_after.status == original_order_status
    assert order_after.payment_status == original_payment_status
    assert ticket_after.status == original_ticket_status
    assert product_after.stock_quantity == original_stock
