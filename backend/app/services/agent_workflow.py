from __future__ import annotations

import inspect
import re
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from app.schemas.agent import (
    AgentAction,
    AgentIntent,
    AgentMode,
    AgentPolicySource,
    AgentProcessRequest,
    AgentProcessResponse,
)
from app.schemas.tools import (
    CreateTicketRequest,
    EscalateTicketRequest,
    OrderInfoResponse,
    RefundEligibilityRequest,
    RefundEligibilityResponse,
    TicketResponse,
)
from app.services import policy_knowledge
from app.services import llm_client
from app.services import tools as tool_service
from app.services.policy_knowledge import PolicySearchMatch
from app.services.tool_errors import ToolError


REQUIRED_NODES = (
    "intent_classification",
    "information_check",
    "policy_retrieval",
    "tool_selection",
    "business_action",
    "response_generation",
    "trace_recording",
)

DEFAULT_AGENT_MODE: AgentMode = "rules"
REFUND_SAFETY_NOTICE = (
    "我这边不会直接为您操作退款，也不会修改支付状态或库存；后续会按平台售后审核结果处理。"
)
HIGH_RISK_REPLY_PATTERNS = (
    "已退款",
    "已经退款",
    "执行退款",
    "真实退款",
    "支付状态已",
    "修改支付状态",
    "库存已",
    "修改库存",
)
SHIPMENT_CARRIER_LABELS = {
    "SF Express": "顺丰速运",
    "JD Logistics": "京东物流",
    "YTO Express": "圆通速递",
    "ZTO Express": "中通快递",
}
SHIPMENT_STATUS_LABELS = {
    "pending_pickup": "待揽收",
    "in_transit": "运输中",
    "delivered": "已签收",
    "exception": "配送异常",
}

PolicySearch = Callable[[str, int], list[PolicySearchMatch]]

INTENT_POLICY_EXPANSIONS: dict[AgentIntent, tuple[str, ...]] = {
    "refund_request": (
        "七天无理由",
        "退货退款",
        "退款到账",
        "退货规则",
        "退款审核",
        "refund",
        "return",
    ),
    "shipping_issue": (
        "物流延迟",
        "物流延迟赔付",
        "快递",
        "运单",
        "承运商",
        "shipping",
        "delivery",
        "delayed",
        "not received",
    ),
    "invoice_request": (
        "发票",
        "发票开具",
        "电子发票",
        "企业抬头",
        "invoice",
    ),
    "account_issue": (
        "会员售后",
        "会员售后权益",
        "账号",
        "账户",
        "登录",
        "密码",
        "身份校验",
        "account",
        "login",
        "password",
    ),
    "complaint": (
        "投诉升级",
        "转人工",
        "人工客服",
        "complaint",
        "escalate",
    ),
    "other": (
        "售后政策",
        "七天无理由",
        "特殊商品",
        "会员售后",
        "退款到账",
    ),
}


@dataclass
class WorkflowState:
    request: AgentProcessRequest
    mode: AgentMode = DEFAULT_AGENT_MODE
    intent: AgentIntent = "other"
    confidence: float = 0.0
    order_number: str | None = None
    external_id: str | None = None
    ticket_number: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    selected_tools: list[str] = field(default_factory=list)
    policy_matches: list[PolicySearchMatch] = field(default_factory=list)
    order_info: OrderInfoResponse | None = None
    refund_check: RefundEligibilityResponse | None = None
    ticket: TicketResponse | None = None
    need_human: bool = False
    ticket_id: str | None = None
    reply: str = ""
    actions: list[AgentAction] = field(default_factory=list)


def process_customer_message(
    session: Session,
    request: AgentProcessRequest,
    policy_search: PolicySearch | None = None,
) -> AgentProcessResponse:
    state = _initial_state(request)
    search = policy_search or _default_policy_search(session)

    _intent_classification(state)
    _information_check(state)
    _policy_retrieval(state, search)
    _tool_selection(state)
    _business_action(state, session)
    _response_generation(state)
    _trace_recording(state)

    return _build_response(state)


def _default_policy_search(session: Session) -> PolicySearch:
    def search(query: str, top_k: int) -> list[PolicySearchMatch]:
        search_function = policy_knowledge.search_policy
        parameters = inspect.signature(search_function).parameters
        if "session" in parameters:
            return search_function(query, top_k, session=session)
        return search_function(query, top_k)

    return search


def _initial_state(request: AgentProcessRequest) -> WorkflowState:
    message = request.message
    return WorkflowState(
        request=request,
        mode=_resolve_agent_mode(request.mode),
        order_number=request.order_number or _find_order_number(message),
        external_id=request.external_id or _find_external_id(message),
        ticket_number=request.ticket_number or _find_ticket_number(message),
    )


def _intent_classification(state: WorkflowState) -> None:
    _classify_intent_with_rules(state)
    _maybe_assist_intent_with_llm(state)

    _append_action(
        state,
        node="intent_classification",
        status="success",
        summary=f"Intent classified as {state.intent}.",
        metadata={"confidence": round(state.confidence, 2)},
    )


def _classify_intent_with_rules(state: WorkflowState) -> None:
    text = state.request.message.lower()
    if _contains_any(text, ("投诉", "不满意", "转人工", "人工处理", "complaint", "escalate")):
        state.intent = "complaint"
        state.confidence = 0.9
    elif _contains_any(text, ("退款", "退货", "退钱", "坏了", "破损", "refund", "return")):
        state.intent = "refund_request"
        state.confidence = 0.84
    elif _contains_any(text, ("物流", "快递", "运单", "没收到", "延迟", "shipping", "delivery")):
        state.intent = "shipping_issue"
        state.confidence = 0.84
    elif _contains_any(text, ("发票", "开票", "invoice")):
        state.intent = "invoice_request"
        state.confidence = 0.82
    elif _contains_any(text, ("账号", "账户", "登录", "密码", "account", "login", "password")):
        state.intent = "account_issue"
        state.confidence = 0.78
    else:
        state.intent = "other"
        state.confidence = 0.45


def _maybe_assist_intent_with_llm(state: WorkflowState) -> None:
    if state.mode != "llm_assisted":
        return
    if state.intent != "other" and state.confidence >= 0.7:
        return

    try:
        assisted_intent = llm_client.classify_intent_with_llm(state.request.message)
    except Exception:
        return

    if assisted_intent is None:
        return

    state.intent = assisted_intent
    state.confidence = max(state.confidence, 0.72)


def _information_check(state: WorkflowState) -> None:
    missing_fields: list[str] = []

    if state.intent in {"refund_request", "shipping_issue", "invoice_request"}:
        if state.order_number is None:
            missing_fields.append("order_number")
    elif state.intent == "complaint":
        if state.order_number is None and state.ticket_number is None:
            missing_fields.append("order_number_or_ticket_number")
    elif state.intent == "account_issue":
        if state.external_id is None:
            missing_fields.append("external_id")

    state.missing_fields = missing_fields
    if missing_fields:
        state.need_human = True
        state.confidence = min(state.confidence, 0.62)

    _append_action(
        state,
        node="information_check",
        status="success" if not missing_fields else "skipped",
        summary=(
            "Required information is complete."
            if not missing_fields
            else f"Missing required fields: {', '.join(missing_fields)}."
        ),
        metadata={"missing_fields": missing_fields},
    )


def _policy_retrieval(state: WorkflowState, policy_search: PolicySearch) -> None:
    query = _policy_search_query(state)
    try:
        state.policy_matches = policy_search(query, 3)
    except Exception as error:  # pragma: no cover - defensive integration guard
        state.policy_matches = []
        state.confidence = min(state.confidence, 0.55)
        _append_action(
            state,
            node="policy_retrieval",
            tool_name="search_policy",
            status="failed",
            summary=f"Policy retrieval failed: {error}.",
        )
        return

    if state.policy_matches and not state.missing_fields:
        state.confidence = min(0.95, state.confidence + 0.05)

    _append_action(
        state,
        node="policy_retrieval",
        tool_name="search_policy",
        status="success",
        summary=f"Retrieved {len(state.policy_matches)} policy source(s).",
        metadata={
            "query": query,
            "policy_titles": [match.policy_title for match in state.policy_matches],
        },
    )


def _tool_selection(state: WorkflowState) -> None:
    if state.missing_fields:
        state.selected_tools = []
    elif state.intent == "refund_request":
        state.selected_tools = [
            "get_order_info",
            "check_refund_eligibility",
            "create_ticket",
        ]
    elif state.intent == "shipping_issue":
        state.selected_tools = ["get_order_info"]
    elif state.intent == "invoice_request":
        state.selected_tools = ["get_order_info", "create_ticket"]
    elif state.intent == "complaint":
        if state.ticket_number:
            state.selected_tools = ["escalate_to_human"]
        else:
            state.selected_tools = ["get_order_info", "create_ticket", "escalate_to_human"]
    else:
        state.selected_tools = []

    _append_action(
        state,
        node="tool_selection",
        status="success" if state.selected_tools else "skipped",
        summary=(
            f"Selected tools: {', '.join(state.selected_tools)}."
            if state.selected_tools
            else "No business tool selected."
        ),
        metadata={"selected_tools": state.selected_tools},
    )


def _business_action(state: WorkflowState, session: Session) -> None:
    if not state.selected_tools:
        _append_action(
            state,
            node="business_action",
            status="skipped",
            summary="Business action skipped.",
        )
        return

    for tool_name in state.selected_tools:
        if tool_name == "get_order_info":
            _run_get_order_info(state, session)
        elif tool_name == "check_refund_eligibility":
            _run_check_refund_eligibility(state, session)
        elif tool_name == "create_ticket":
            _run_create_ticket(state, session)
        elif tool_name == "escalate_to_human":
            _run_escalate_to_human(state, session)


def _run_get_order_info(state: WorkflowState, session: Session) -> None:
    if state.order_number is None:
        _append_action(
            state,
            node="business_action",
            tool_name="get_order_info",
            status="skipped",
            summary="Order lookup skipped because order number is missing.",
        )
        return

    try:
        state.order_info = tool_service.get_order_info(session, state.order_number)
        state.external_id = state.external_id or state.order_info.user.external_id
    except ToolError as error:
        _record_tool_error(state, "get_order_info", error)
        return

    _append_action(
        state,
        node="business_action",
        tool_name="get_order_info",
        status="success",
        summary=f"Loaded order {state.order_info.order_number}.",
        metadata={
            "order_status": state.order_info.status,
            "payment_status": state.order_info.payment_status,
            "external_id": state.order_info.user.external_id,
        },
    )


def _run_check_refund_eligibility(state: WorkflowState, session: Session) -> None:
    if state.order_number is None:
        _append_action(
            state,
            node="business_action",
            tool_name="check_refund_eligibility",
            status="skipped",
            summary="Refund eligibility check skipped because order number is missing.",
        )
        return

    try:
        state.refund_check = tool_service.check_refund_eligibility(
            session,
            RefundEligibilityRequest(
                order_number=state.order_number,
                reason=state.request.message,
                requested_amount=state.request.requested_amount,
            ),
        )
    except ToolError as error:
        _record_tool_error(state, "check_refund_eligibility", error)
        return

    _append_action(
        state,
        node="business_action",
        tool_name="check_refund_eligibility",
        status="success",
        summary=(
            "Refund eligibility checked; no refund or payment state was changed."
        ),
        metadata={
            "eligible": state.refund_check.eligible,
            "recommendation": state.refund_check.recommendation,
            "high_risk_action_executed": state.refund_check.high_risk_action_executed,
        },
    )


def _run_create_ticket(state: WorkflowState, session: Session) -> None:
    if state.order_number is None or state.external_id is None:
        state.need_human = True
        state.confidence = min(state.confidence, 0.55)
        _append_action(
            state,
            node="business_action",
            tool_name="create_ticket",
            status="skipped",
            summary="Ticket creation skipped because order number or user id is missing.",
        )
        return

    try:
        state.ticket = tool_service.create_ticket(
            session,
            CreateTicketRequest(
                order_number=state.order_number,
                external_id=state.external_id,
                category=_ticket_category(state.intent),
                priority="high" if state.intent == "complaint" else "medium",
                subject=_ticket_subject(state),
                description=state.request.message,
            ),
        )
        state.ticket_id = state.ticket.ticket_number
    except ToolError as error:
        _record_tool_error(state, "create_ticket", error)
        return

    _append_action(
        state,
        node="business_action",
        tool_name="create_ticket",
        status="success",
        summary=f"Created ticket {state.ticket_id}.",
        metadata={
            "ticket_id": state.ticket_id,
            "category": state.ticket.category,
            "status": state.ticket.status,
        },
    )


def _run_escalate_to_human(state: WorkflowState, session: Session) -> None:
    ticket_number = state.ticket_id or state.ticket_number
    if ticket_number is None:
        state.need_human = True
        state.confidence = min(state.confidence, 0.55)
        _append_action(
            state,
            node="business_action",
            tool_name="escalate_to_human",
            status="skipped",
            summary="Human escalation skipped because ticket number is missing.",
        )
        return

    try:
        escalated = tool_service.escalate_to_human(
            session,
            ticket_number,
            EscalateTicketRequest(reason=state.request.message),
        )
        state.ticket_id = escalated.ticket_number
        state.need_human = True
    except ToolError as error:
        _record_tool_error(state, "escalate_to_human", error)
        return

    _append_action(
        state,
        node="business_action",
        tool_name="escalate_to_human",
        status="success",
        summary=f"Escalated ticket {state.ticket_id} to human support.",
        metadata={"ticket_id": state.ticket_id, "handled_by_ai": False},
    )


def _response_generation(state: WorkflowState) -> None:
    if state.missing_fields:
        state.reply = _missing_information_reply(state)
    elif state.intent == "refund_request":
        state.reply = _refund_reply(state)
    elif state.intent == "shipping_issue":
        state.reply = _shipping_reply(state)
    elif state.intent == "invoice_request":
        state.reply = _invoice_reply(state)
    elif state.intent == "account_issue":
        state.reply = _account_reply(state)
    elif state.intent == "complaint":
        state.reply = _complaint_reply(state)
    else:
        state.reply = "我已查询相关售后政策。你可以继续补充订单、物流、发票或账号问题细节，我会继续协助处理。"

    state.reply = _maybe_polish_reply_with_llm(state, state.reply)

    _append_action(
        state,
        node="response_generation",
        status="success",
        summary="Generated customer service reply.",
    )


def _trace_recording(state: WorkflowState) -> None:
    _append_action(
        state,
        node="trace_recording",
        status="success",
        summary=f"Recorded workflow trace with {len(state.actions)} prior action(s).",
        metadata={"node_sequence": list(REQUIRED_NODES)},
    )


def _build_response(state: WorkflowState) -> AgentProcessResponse:
    return AgentProcessResponse(
        intent=state.intent,
        reply=state.reply,
        actions=state.actions,
        policy_sources=[
            AgentPolicySource(
                policy_title=match.policy_title,
                source_file=match.source_file,
                score=match.score,
            )
            for match in state.policy_matches
        ],
        need_human=state.need_human,
        ticket_id=state.ticket_id,
        confidence=round(max(0.0, min(1.0, state.confidence)), 2),
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _resolve_agent_mode(request_mode: AgentMode | None) -> AgentMode:
    if request_mode is not None:
        return request_mode
    env_mode = os.getenv("AGENT_MODE", DEFAULT_AGENT_MODE).strip().lower()
    return "llm_assisted" if env_mode == "llm_assisted" else "rules"


def _policy_search_query(state: WorkflowState) -> str:
    expansion = " ".join(INTENT_POLICY_EXPANSIONS[state.intent])
    return f"{state.request.message} {expansion}".strip()


def _find_order_number(message: str) -> str | None:
    match = re.search(r"\bORD-\d{4}-\d{4}\b", message, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _find_ticket_number(message: str) -> str | None:
    match = re.search(r"\bTCK-\d{4}-\d{4}\b", message, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _find_external_id(message: str) -> str | None:
    match = re.search(r"\bU\d{4}\b", message, flags=re.IGNORECASE)
    return match.group(0).upper() if match else None


def _ticket_category(intent: AgentIntent) -> str:
    return {
        "refund_request": "refund",
        "shipping_issue": "delivery",
        "invoice_request": "invoice",
        "account_issue": "account",
        "complaint": "complaint",
        "other": "general",
    }[intent]


def _ticket_subject(state: WorkflowState) -> str:
    order_number = state.order_number or "unknown order"
    return {
        "refund_request": f"Refund review for {order_number}",
        "invoice_request": f"Invoice request for {order_number}",
        "complaint": f"Complaint escalation for {order_number}",
    }.get(state.intent, f"Customer support request for {order_number}")


def _missing_information_reply(state: WorkflowState) -> str:
    if "order_number" in state.missing_fields:
        return "为了继续处理这个问题，请先提供订单号。拿到订单号后，我可以继续查询订单、政策和可执行的客服动作。"
    if "order_number_or_ticket_number" in state.missing_fields:
        return "为了安排人工继续处理投诉，请提供订单号或已有工单号。"
    if "external_id" in state.missing_fields:
        return "为了处理账号问题，请提供用户编号或账号绑定信息，我会继续协助定位并转人工处理需要人工验证的部分。"
    return "还需要补充必要信息后才能继续处理。"


def _refund_reply(state: WorkflowState) -> str:
    if state.refund_check is None:
        state.need_human = True
        return "您好，这笔退款申请还需要进一步核实订单信息，我会建议转人工客服继续为您确认。"

    reason_text = _refund_reason_text(state.refund_check.reasons)
    if state.refund_check.recommendation == "approve_review":
        return (
            "您好，已帮您核对订单状态，当前订单可以进入退款审核。"
            f"{reason_text}"
            "请您保留商品问题照片或相关凭证，后续以售后审核结果为准。"
            f"{REFUND_SAFETY_NOTICE}"
        )
    if state.refund_check.recommendation == "manual_review":
        return (
            "您好，这笔退款申请需要进一步审核。"
            f"{reason_text}"
            "请您耐心等待审核结果，如有商品问题照片或其他凭证，也可以继续补充。"
            f"{REFUND_SAFETY_NOTICE}"
        )
    return (
        "您好，已帮您核对订单状态，当前暂不满足直接进入退款审核的条件。"
        f"{reason_text}"
        "如果您还有商品破损、少件或其他凭证，可以继续补充给客服复核。"
        f"{REFUND_SAFETY_NOTICE}"
    )


def _maybe_polish_reply_with_llm(state: WorkflowState, rule_reply: str) -> str:
    if state.mode != "llm_assisted":
        return _ensure_refund_safety_notice(state, rule_reply)

    try:
        polished = llm_client.polish_reply_with_llm(
            message=state.request.message,
            rule_reply=rule_reply,
            intent=state.intent,
            need_human=state.need_human,
        )
    except Exception:
        return _ensure_refund_safety_notice(state, rule_reply)

    if polished is None or _contains_high_risk_claim(polished):
        return _ensure_refund_safety_notice(state, rule_reply)
    return _ensure_refund_safety_notice(state, polished)


def _ensure_refund_safety_notice(state: WorkflowState, reply: str) -> str:
    if state.intent != "refund_request":
        return reply
    if REFUND_SAFETY_NOTICE in reply:
        return reply
    return f"{reply.rstrip()} {REFUND_SAFETY_NOTICE}"


def _contains_high_risk_claim(reply: str) -> bool:
    return any(pattern in reply for pattern in HIGH_RISK_REPLY_PATTERNS)


def _shipping_reply(state: WorkflowState) -> str:
    if state.order_info is None:
        state.need_human = True
        return "您好，这笔订单的物流信息暂时没有查询成功，我会建议转人工客服继续为您核实。"

    if not state.order_info.shipments:
        return (
            f"您好，订单 {state.order_info.order_number} 当前还没有查到关联物流记录。"
            "建议您稍后再查看；如果长时间没有更新，我会建议转人工客服帮您核实发货状态。"
        )

    shipment = state.order_info.shipments[0]
    return (
        f"您好，已帮您查到订单 {state.order_info.order_number} 的物流信息："
        f"{_shipment_carrier_label(shipment.carrier)}，运单 {shipment.tracking_number}，"
        f"当前状态 {_shipment_status_label(shipment.status)}，"
        f"最新节点为{_shipment_checkpoint_label(shipment.last_checkpoint)}。"
        "请您先确认是否已经收到包裹；如果仍未收到或物流状态与实际不符，我会建议转人工客服继续核实。"
    )


def _invoice_reply(state: WorkflowState) -> str:
    if state.ticket_id:
        return (
            f"您好，已收到订单 {state.order_number} 的开票申请，会为您进入后续开票处理。"
            "请您留意后续处理结果；如果需要补充发票抬头、税号或接收邮箱，也可以继续发给我。"
        )
    state.need_human = True
    return "您好，您的开票申请还需要客服进一步确认，我会建议转人工客服继续为您处理。"


def _account_reply(state: WorkflowState) -> str:
    state.need_human = True
    return "账号问题通常需要身份校验，我会建议转人工处理。请准备用户编号、手机号或邮箱等可验证信息。"


def _complaint_reply(state: WorkflowState) -> str:
    state.need_human = True
    if state.ticket_id:
        return (
            "抱歉这次售后处理给您带来了不好的体验，已为您转接人工客服继续跟进。"
            "请您保持联系方式畅通，我们会尽快核实并处理。"
        )
    return "抱歉给您带来不好的体验。请您补充订单号或相关问题信息，我会继续帮您转人工客服跟进。"


def _record_tool_error(state: WorkflowState, tool_name: str, error: ToolError) -> None:
    state.need_human = True
    state.confidence = min(state.confidence, 0.55)
    _append_action(
        state,
        node="business_action",
        tool_name=tool_name,
        status="failed",
        summary=f"{tool_name} failed: {error.code} - {error.message}",
        metadata={"error_code": error.code},
    )


def _shipment_carrier_label(carrier: str) -> str:
    return SHIPMENT_CARRIER_LABELS.get(carrier, carrier)


def _shipment_status_label(status: str) -> str:
    return SHIPMENT_STATUS_LABELS.get(status, status)


def _shipment_checkpoint_label(checkpoint: str) -> str:
    if checkpoint.startswith("Checkpoint "):
        return f"物流节点 {checkpoint.removeprefix('Checkpoint ')}"
    return checkpoint


def _refund_reason_text(reasons: list[str]) -> str:
    if not reasons:
        return ""

    localized = [_refund_reason_label(reason) for reason in reasons]
    return f"核对结果：{'；'.join(localized)}。"


def _refund_reason_label(reason: str) -> str:
    if reason == "Order is paid and within a refundable status.":
        return "订单已支付，且当前订单状态支持售后审核"
    if reason == "Requested refund amount exceeds the order total.":
        return "申请金额超过订单实付金额"
    if reason.startswith("Payment status is ") and reason.endswith(", not paid."):
        status = reason.removeprefix("Payment status is ").removesuffix(", not paid.")
        return f"当前支付状态为{status}，暂不支持退款审核"
    if reason.startswith("Order status is already ") and reason.endswith("."):
        status = reason.removeprefix("Order status is already ").removesuffix(".")
        return f"当前订单状态已为{status}，需要客服复核"
    return reason


def _append_action(
    state: WorkflowState,
    node: str,
    status: str,
    summary: str,
    tool_name: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    state.actions.append(
        AgentAction(
            node=node,
            tool_name=tool_name,
            status=status,  # type: ignore[arg-type]
            summary=summary,
            metadata=metadata or {},
        )
    )
