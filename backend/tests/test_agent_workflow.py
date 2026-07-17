from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, Ticket
from app.schemas.agent import AgentProcessRequest
from app.services.agent_workflow import REQUIRED_NODES, process_customer_message
from app.services.policy_knowledge import PolicySearchMatch


def fake_policy_search(query: str, top_k: int = 3) -> list[PolicySearchMatch]:
    del top_k
    title = "七天无理由退货规则"
    source = "seven_day_return.md"
    if "物流" in query or "快递" in query:
        title = "物流延迟赔付规则"
        source = "shipping_delay_compensation.md"
    if "发票" in query:
        title = "发票开具规则"
        source = "invoice.md"
    if "投诉" in query:
        title = "投诉升级规则"
        source = "complaint_escalation.md"

    return [
        PolicySearchMatch(
            policy_title=title,
            matched_text=f"{title} matched text",
            score=0.91,
            source_file=source,
        )
    ]


def test_agent_request_accepts_optional_processing_mode() -> None:
    rules_request = AgentProcessRequest(message="你好", mode="rules")
    llm_request = AgentProcessRequest(message="你好", mode="llm_assisted")
    omitted_request = AgentProcessRequest(message="你好")

    assert rules_request.mode == "rules"
    assert llm_request.mode == "llm_assisted"
    assert omitted_request.mode is None


def test_agent_request_rejects_invalid_processing_mode() -> None:
    with pytest.raises(ValidationError):
        AgentProcessRequest(message="你好", mode="auto")  # type: ignore[arg-type]


def test_refund_request_runs_policy_order_and_refund_tools_without_changing_order(
    tools_db_session: Session,
) -> None:
    before = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )
    assert before is not None
    original_status = before.status
    original_payment_status = before.payment_status

    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="我收到的商品坏了，想申请退款",
            order_number="ORD-2026-0002",
            requested_amount=Decimal("50.00"),
        ),
        policy_search=fake_policy_search,
    )

    tools_db_session.expire_all()
    after = tools_db_session.scalar(
        select(Order).where(Order.order_number == "ORD-2026-0002")
    )

    assert result.intent == "refund_request"
    assert result.need_human is False
    assert result.ticket_id is not None
    assert result.confidence >= 0.8
    assert "您好" in result.reply
    assert "退款审核" in result.reply
    assert "不会直接为您操作退款" in result.reply
    assert "退款资格" not in result.reply
    assert "本流程只给出" not in result.reply
    assert [action.tool_name for action in result.actions if action.tool_name] == [
        "search_policy",
        "get_order_info",
        "check_refund_eligibility",
        "create_ticket",
    ]
    assert after is not None
    assert after.status == original_status
    assert after.payment_status == original_payment_status

    ticket = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == result.ticket_id)
    )
    assert ticket is not None
    assert ticket.category == "refund"
    assert ticket.status == "open"


def test_refund_request_missing_order_number_asks_for_more_information(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(message="我要退款，订单是多少我忘了"),
        policy_search=fake_policy_search,
    )

    assert result.intent == "refund_request"
    assert result.need_human is True
    assert result.ticket_id is None
    assert result.confidence < 0.8
    assert "订单号" in result.reply
    assert "check_refund_eligibility" not in [
        action.tool_name for action in result.actions
    ]


def test_llm_assisted_mode_without_api_key_falls_back_to_rules(
    tools_db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    rules_result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="ORD-2026-0002 商品坏了我要退款",
            requested_amount=Decimal("50.00"),
            mode="rules",
        ),
        policy_search=fake_policy_search,
    )
    llm_result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="ORD-2026-0002 商品坏了我要退款",
            requested_amount=Decimal("50.00"),
            mode="llm_assisted",
        ),
        policy_search=fake_policy_search,
    )

    assert llm_result.intent == rules_result.intent
    assert llm_result.reply == rules_result.reply
    assert [action.tool_name for action in llm_result.actions if action.tool_name] == [
        "search_policy",
        "get_order_info",
        "check_refund_eligibility",
        "create_ticket",
    ]


def test_llm_exception_falls_back_to_rules_output(
    tools_db_session: Session,
    monkeypatch,
) -> None:
    def raise_classification_error(_message: str):
        raise RuntimeError("llm failed")

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.agent_workflow.llm_client.classify_intent_with_llm",
        raise_classification_error,
    )
    monkeypatch.setattr(
        "app.services.agent_workflow.llm_client.polish_reply_with_llm",
        lambda *_args, **_kwargs: None,
    )

    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(message="你好，我想了解售后政策", mode="llm_assisted"),
        policy_search=fake_policy_search,
    )

    assert result.intent == "other"
    assert "可以继续补充" in result.reply


def test_llm_polish_cannot_replace_refund_safety_notice(
    tools_db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(
        "app.services.agent_workflow.llm_client.classify_intent_with_llm",
        lambda _message: None,
    )
    monkeypatch.setattr(
        "app.services.agent_workflow.llm_client.polish_reply_with_llm",
        lambda *_args, **_kwargs: "已为你执行退款并修改库存。",
    )

    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="ORD-2026-0002 商品坏了我要退款",
            requested_amount=Decimal("50.00"),
            mode="llm_assisted",
        ),
        policy_search=fake_policy_search,
    )

    assert "已为你执行退款并修改库存" not in result.reply
    assert "不会直接为您操作退款" in result.reply
    assert "不会修改支付状态或库存" in result.reply
    assert [action.tool_name for action in result.actions if action.tool_name] == [
        "search_policy",
        "get_order_info",
        "check_refund_eligibility",
        "create_ticket",
    ]


def test_shipping_issue_uses_order_info_and_policy_sources(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="订单 ORD-2026-0001 的物流一直没更新，帮我看看快递",
        ),
        policy_search=fake_policy_search,
    )

    assert result.intent == "shipping_issue"
    assert result.need_human is False
    assert "物流" in result.reply
    assert "京东物流" in result.reply
    assert "已签收" in result.reply
    assert "物流节点 01" in result.reply
    assert "请您先确认是否已经收到包裹" in result.reply
    assert "JD Logistics" not in result.reply
    assert "delivered" not in result.reply
    assert "Checkpoint" not in result.reply
    assert "同步检索" not in result.reply
    assert "处理参考" not in result.reply
    assert any(action.tool_name == "get_order_info" for action in result.actions)
    assert result.policy_sources[0].policy_title == "物流延迟赔付规则"


def test_policy_retrieval_expands_shipping_query_with_policy_keywords(
    tools_db_session: Session,
) -> None:
    captured_queries: list[str] = []

    def search_requires_expansion(query: str, top_k: int = 3) -> list[PolicySearchMatch]:
        del top_k
        captured_queries.append(query)
        if "物流延迟" not in query:
            return []
        return [
            PolicySearchMatch(
                policy_title="物流延迟赔付规则",
                matched_text="物流延迟 matched text",
                score=0.99,
                source_file="logistics_delay_compensation.md",
            )
        ]

    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="ORD-2026-0036 shipping delivery 一直没到，帮我看物流状态",
        ),
        policy_search=search_requires_expansion,
    )

    assert "物流延迟" in captured_queries[0]
    assert result.intent == "shipping_issue"
    assert result.policy_sources[0].policy_title == "物流延迟赔付规则"


def test_policy_retrieval_expands_account_query_with_member_keywords(
    tools_db_session: Session,
) -> None:
    captured_queries: list[str] = []

    def search_requires_expansion(query: str, top_k: int = 3) -> list[PolicySearchMatch]:
        del top_k
        captured_queries.append(query)
        if "会员售后" not in query:
            return []
        return [
            PolicySearchMatch(
                policy_title="会员售后权益",
                matched_text="会员售后 matched text",
                score=0.99,
                source_file="member_after_sales_rights.md",
            )
        ]

    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="account login password 都失败，U0020 需要人工校验",
        ),
        policy_search=search_requires_expansion,
    )

    assert "会员售后" in captured_queries[0]
    assert result.intent == "account_issue"
    assert result.policy_sources[0].policy_title == "会员售后权益"


def test_invoice_request_creates_invoice_ticket_when_order_is_known(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="请帮我给 ORD-2026-0031 开一张发票",
            external_id="U0001",
        ),
        policy_search=fake_policy_search,
    )

    assert result.intent == "invoice_request"
    assert result.ticket_id is not None
    assert result.need_human is False
    assert "您好" in result.reply
    assert "开票申请" in result.reply
    assert "请您留意后续处理结果" in result.reply
    assert "创建发票处理工单" not in result.reply
    assert "发票政策" not in result.reply
    assert any(action.tool_name == "create_ticket" for action in result.actions)

    ticket = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == result.ticket_id)
    )
    assert ticket is not None
    assert ticket.category == "invoice"
    assert ticket.status == "open"


def test_account_issue_requires_user_identifier(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(message="我的账号登录不了，密码也重置失败"),
        policy_search=fake_policy_search,
    )

    assert result.intent == "account_issue"
    assert result.need_human is True
    assert result.ticket_id is None
    assert "用户编号" in result.reply


def test_complaint_creates_ticket_and_escalates_to_human(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="我要投诉，ORD-2026-0031 的售后处理太慢了",
            external_id="U0001",
        ),
        policy_search=fake_policy_search,
    )

    assert result.intent == "complaint"
    assert result.need_human is True
    assert result.ticket_id is not None
    assert "抱歉" in result.reply
    assert "已为您转接人工客服" in result.reply
    assert "请您保持联系方式畅通" in result.reply
    assert "升级给人工客服处理" not in result.reply
    assert "工单" not in result.reply
    assert any(action.tool_name == "create_ticket" for action in result.actions)
    assert any(action.tool_name == "escalate_to_human" for action in result.actions)

    ticket = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == result.ticket_id)
    )
    assert ticket is not None
    assert ticket.status == "escalated"


def test_complaint_can_escalate_existing_ticket(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="我要投诉，请直接转人工处理 TCK-2026-0001",
            ticket_number="TCK-2026-0001",
        ),
        policy_search=fake_policy_search,
    )

    assert result.intent == "complaint"
    assert result.need_human is True
    assert result.ticket_id == "TCK-2026-0001"
    assert any(action.tool_name == "escalate_to_human" for action in result.actions)

    ticket = tools_db_session.scalar(
        select(Ticket).where(Ticket.ticket_number == "TCK-2026-0001")
    )
    assert ticket is not None
    assert ticket.status == "escalated"


def test_other_intent_returns_safe_general_reply(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(message="你好，我想了解售后政策"),
        policy_search=fake_policy_search,
    )

    assert result.intent == "other"
    assert result.need_human is False
    assert result.ticket_id is None
    assert "可以继续补充" in result.reply


def test_workflow_records_all_required_nodes_in_order(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(
            message="订单 ORD-2026-0001 的物流为什么还没到",
        ),
        policy_search=fake_policy_search,
    )

    first_seen_nodes = []
    for action in result.actions:
        if action.node not in first_seen_nodes:
            first_seen_nodes.append(action.node)

    assert first_seen_nodes == list(REQUIRED_NODES)
    assert result.actions[-1].node == "trace_recording"


def test_policy_sources_are_projected_from_search_results(
    tools_db_session: Session,
) -> None:
    result = process_customer_message(
        tools_db_session,
        AgentProcessRequest(message="请问七天内可以退货退款吗", order_number="ORD-2026-0002"),
        policy_search=fake_policy_search,
    )

    assert len(result.policy_sources) == 1
    source = result.policy_sources[0]
    assert source.policy_title == "七天无理由退货规则"
    assert source.source_file == "seven_day_return.md"
    assert source.score == 0.91


def test_agent_api_returns_required_json_shape(
    tools_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.agent_workflow.policy_knowledge.search_policy",
        fake_policy_search,
    )

    response = tools_client.post(
        "/api/agent/process",
        json={
            "message": "ORD-2026-0002 商品坏了我要退款",
            "requested_amount": "50.00",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
        "intent",
        "reply",
        "actions",
        "policy_sources",
        "need_human",
        "ticket_id",
        "confidence",
    }
    assert data["intent"] == "refund_request"
    assert isinstance(data["reply"], str)
    assert isinstance(data["actions"], list)
    assert isinstance(data["policy_sources"], list)
    assert data["need_human"] is False
    assert data["ticket_id"]
    assert data["confidence"] >= 0.8
