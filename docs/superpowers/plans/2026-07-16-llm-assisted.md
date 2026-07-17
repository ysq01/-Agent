# LLM-Assisted Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, front-end-toggleable LLM-assisted mode that helps with intent understanding and reply polishing while preserving the deterministic rules workflow and safety boundaries.

**Architecture:** The existing rules state machine remains the control plane. The front end persists a business-facing "智能增强" preference in `localStorage` and sends `mode` with each Agent request. The backend resolves `rules` versus `llm_assisted`, calls a tiny optional Alibaba Cloud DashScope client only at intent classification and reply polishing boundaries, and falls back to rules whenever the LLM is unavailable or unsafe.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Qdrant, Python standard-library `urllib.request`, React, TypeScript, Vite, localStorage.

## Global Constraints

- Default mode is `rules`.
- `llm_assisted` is optional and must work as a no-op fallback without `DASHSCOPE_API_KEY`.
- Do not replace the rule state machine.
- Do not introduce LangGraph.
- Do not add a mandatory LLM provider SDK dependency.
- Do not let the LLM select or execute business tools.
- Do not let the LLM execute or authorize refunds, payment updates, inventory changes, or ticket state changes.
- All business facts still come from tool APIs, PostgreSQL, and Qdrant policy retrieval.
- All high-risk decisions still come from deterministic rules and tool validation.
- Keep `AgentProcessResponse` unchanged.
- Do not expose API keys, model names, raw JSON, internal tool names, or developer diagnostics in the customer service front end.
- The front-end "智能增强" preference is persisted in browser `localStorage`.
- Refund replies must preserve: `本流程只给出审核建议，不会真实执行退款，也不会修改支付状态或库存。`
- Keep the existing 50-case rules evaluation baseline passing.
- Current workspace path `E:\code3\kefuAgent` is not a git repository; replace commit steps with changed-file notes and verification results.

---

## File Structure

- `backend/app/schemas/agent.py`: add `AgentMode` and optional request `mode`.
- `backend/app/services/llm_client.py`: create a focused optional Alibaba Cloud DashScope OpenAI-compatible chat completions client.
- `backend/app/services/agent_workflow.py`: resolve mode and insert LLM assistance at intent and reply boundaries only.
- `backend/app/services/evaluation.py`: allow evaluation to pass a mode into Agent requests while defaulting to rules.
- `backend/scripts/run_eval.py`: add `--mode rules|llm_assisted`, default `rules`.
- `backend/tests/test_llm_client.py`: test no-key behavior, response parsing, exceptions, and polishing fallback primitives.
- `backend/tests/test_agent_workflow.py`: test request mode validation, fallback behavior, safe workflow integration, and refund safety wording.
- `backend/tests/test_evaluation.py`: test evaluation forwards default and requested mode.
- `frontend/src/types.ts`: add front-end `AgentMode` and optional request `mode`.
- `frontend/src/App.tsx`: add persisted "智能增强" toggle and send the selected mode.
- `frontend/src/styles.css`: style the compact toggle without changing the app structure.
- `README.md`, `docs/architecture.md`, `docs/demo-guide.md`: document mode configuration, front-end toggle, no-key fallback, and safety boundaries.

---

### Task 1: Request Mode Schema

**Files:**
- Modify: `backend/app/schemas/agent.py`
- Modify: `backend/tests/test_agent_workflow.py`

**Interfaces:**
- Produces: `AgentMode = Literal["rules", "llm_assisted"]`
- Produces: `AgentProcessRequest.mode: AgentMode | None = None`
- Consumes: existing `AgentProcessRequest` construction throughout tests and services.

- [ ] **Step 1: Write failing schema tests**

Append these tests to `backend/tests/test_agent_workflow.py`:

```python
import pytest
from pydantic import ValidationError
```

```python
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
```

- [ ] **Step 2: Run schema tests and confirm failure**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_agent_workflow.py::test_agent_request_accepts_optional_processing_mode tests\test_agent_workflow.py::test_agent_request_rejects_invalid_processing_mode -q -p no:cacheprovider
```

Expected: first test fails because `mode` is not currently defined or retained on `AgentProcessRequest`.

- [ ] **Step 3: Implement schema field**

Edit `backend/app/schemas/agent.py`:

```python
AgentMode = Literal["rules", "llm_assisted"]
```

Then update `AgentProcessRequest`:

```python
class AgentProcessRequest(AgentSchema):
    message: str = Field(min_length=1)
    order_number: str | None = None
    external_id: str | None = None
    ticket_number: str | None = None
    requested_amount: Decimal | None = Field(default=None, gt=0)
    mode: AgentMode | None = None
```

- [ ] **Step 4: Run schema tests and confirm pass**

Run the same command from Step 2.

Expected: both tests pass.

- [ ] **Step 5: Record changed files**

Record:

```text
Changed: backend/app/schemas/agent.py
Changed: backend/tests/test_agent_workflow.py
Verification: schema tests pass
Git commit skipped because E:\code3\kefuAgent is not a git repository.
```

---

### Task 2: Optional LLM Client

**Files:**
- Create: `backend/app/services/llm_client.py`
- Create: `backend/tests/test_llm_client.py`

**Interfaces:**
- Consumes: `AgentIntent` from `app.schemas.agent`
- Produces: `classify_intent_with_llm(message: str) -> AgentIntent | None`
- Produces: `polish_reply_with_llm(message: str, rule_reply: str, intent: AgentIntent, need_human: bool) -> str | None`
- Produces: `_extract_response_text(payload: dict[str, object]) -> str | None`

- [ ] **Step 1: Write failing no-key and parser tests**

Create `backend/tests/test_llm_client.py`:

```python
from app.services import llm_client


def test_classify_intent_returns_none_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    assert llm_client.classify_intent_with_llm("这个订单一直没收到") is None


def test_extract_response_text_reads_chat_completion_choice() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "shipping_issue",
                }
            }
        ]
    }

    assert llm_client._extract_response_text(payload) == "shipping_issue"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_llm_client.py -q -p no:cacheprovider
```

Expected: import fails because `app.services.llm_client` does not exist.

- [ ] **Step 3: Implement the initial client**

Create `backend/app/services/llm_client.py`:

```python
from __future__ import annotations

import json
import os
from typing import Any, get_args
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from app.schemas.agent import AgentIntent


DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_DASHSCOPE_MODEL = "qwen-plus"
DEFAULT_TIMEOUT_SECONDS = 8.0
ALLOWED_INTENTS = set(get_args(AgentIntent))


def classify_intent_with_llm(message: str) -> AgentIntent | None:
    instructions = (
        "你是电商售后客服意图识别助手。只能输出一个意图值："
        "refund_request, shipping_issue, invoice_request, account_issue, complaint, other。"
        "不要输出解释。不能决定退款、支付、库存或工单动作。"
    )
    text = _call_chat_completions_api(
        instructions=instructions,
        input_text=f"用户原话：{message}",
        max_output_tokens=20,
    )
    if text is None:
        return None

    normalized = _parse_intent(text)
    if normalized in ALLOWED_INTENTS:
        return normalized  # type: ignore[return-value]
    return None


def polish_reply_with_llm(
    message: str,
    rule_reply: str,
    intent: AgentIntent,
    need_human: bool,
) -> str | None:
    instructions = (
        "你是电商售后客服回复润色助手。只能润色表达，不能新增业务事实，"
        "不能承诺已经退款，不能修改支付状态，不能修改库存，不能改变是否转人工。"
        "输出一段中文客服回复，不要输出 JSON。"
    )
    text = _call_chat_completions_api(
        instructions=instructions,
        input_text=(
            f"用户原话：{message}\n"
            f"问题类型：{intent}\n"
            f"是否需要人工：{need_human}\n"
            f"规则回复：{rule_reply}"
        ),
        max_output_tokens=220,
    )
    return text.strip() if text and text.strip() else None


def _call_chat_completions_api(
    instructions: str,
    input_text: str,
    max_output_tokens: int,
) -> str | None:
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        return None

    payload = {
        "model": os.getenv("DASHSCOPE_MODEL", DEFAULT_DASHSCOPE_MODEL),
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": input_text},
        ],
        "max_output_tokens": max_output_tokens,
    }

    try:
        response_payload = _post_json(api_key, payload)
    except (OSError, ValueError, HTTPError, URLError, TimeoutError):
        return None

    return _extract_response_text(response_payload)


def _post_json(api_key: str, payload: dict[str, object]) -> dict[str, Any]:
    base_url = os.getenv("DASHSCOPE_BASE_URL", DEFAULT_DASHSCOPE_BASE_URL).rstrip("/")
    timeout = _timeout_seconds()
    body = json.dumps(payload).encode("utf-8")
    request = urlrequest.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlrequest.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_response_text(payload: dict[str, Any]) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content.strip() if isinstance(content, str) and content.strip() else None


def _parse_intent(text: str) -> str:
    stripped = text.strip().strip('"').strip("'")
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        decoded = None

    if isinstance(decoded, dict):
        value = decoded.get("intent")
        if isinstance(value, str):
            return value.strip()
    if isinstance(decoded, str):
        return decoded.strip()

    for intent in ALLOWED_INTENTS:
        if intent in stripped:
            return intent
    return stripped


def _timeout_seconds() -> float:
    raw_value = os.getenv("DASHSCOPE_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return min(max(value, 1.0), 30.0)
```

- [ ] **Step 4: Run client tests and confirm pass**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_llm_client.py -q -p no:cacheprovider
```

Expected: all client tests pass.

- [ ] **Step 5: Add exception and intent parsing tests**

Append to `backend/tests/test_llm_client.py`:

```python
def test_classify_intent_parses_json_response(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(
        llm_client,
        "_post_json",
        lambda _api_key, _payload: {
            "choices": [{"message": {"content": '{"intent": "invoice_request"}'}}]
        },
    )

    assert llm_client.classify_intent_with_llm("我要开票") == "invoice_request"


def test_classify_intent_returns_none_on_client_exception(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    def raise_error(_api_key: str, _payload: dict[str, object]) -> dict[str, object]:
        raise OSError("network down")

    monkeypatch.setattr(llm_client, "_post_json", raise_error)

    assert llm_client.classify_intent_with_llm("我要开票") is None


def test_polish_reply_returns_none_on_empty_response(monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(
        llm_client,
        "_post_json",
        lambda _api_key, _payload: {"choices": [{"message": {"content": "   "}}]},
    )

    assert (
        llm_client.polish_reply_with_llm(
            message="我要退款",
            rule_reply="规则回复",
            intent="refund_request",
            need_human=False,
        )
        is None
    )
```

- [ ] **Step 6: Run client tests again**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_llm_client.py -q -p no:cacheprovider
```

Expected: all client tests pass.

- [ ] **Step 7: Record changed files**

Record:

```text
Created: backend/app/services/llm_client.py
Created: backend/tests/test_llm_client.py
Verification: LLM client tests pass
Git commit skipped because E:\code3\kefuAgent is not a git repository.
```

---

### Task 3: Workflow Mode Resolution and LLM Assistance

**Files:**
- Modify: `backend/app/services/agent_workflow.py`
- Modify: `backend/tests/test_agent_workflow.py`

**Interfaces:**
- Consumes: `AgentProcessRequest.mode`
- Consumes: `llm_client.classify_intent_with_llm(message: str) -> AgentIntent | None`
- Consumes: `llm_client.polish_reply_with_llm(message: str, rule_reply: str, intent: AgentIntent, need_human: bool) -> str | None`
- Produces: `_resolve_agent_mode(request_mode: AgentMode | None) -> AgentMode`
- Produces: `_ensure_refund_safety_notice(state: WorkflowState, reply: str) -> str`
- Produces: `_contains_high_risk_claim(reply: str) -> bool`

- [ ] **Step 1: Write failing fallback and safety tests**

Append to `backend/tests/test_agent_workflow.py`:

```python
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
```

```python
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
    assert "不会真实执行退款" in result.reply
    assert "不会修改支付状态或库存" in result.reply
    assert [action.tool_name for action in result.actions if action.tool_name] == [
        "search_policy",
        "get_order_info",
        "check_refund_eligibility",
    ]
```

- [ ] **Step 2: Run workflow tests and confirm failure**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_agent_workflow.py::test_llm_assisted_mode_without_api_key_falls_back_to_rules tests\test_agent_workflow.py::test_llm_exception_falls_back_to_rules_output tests\test_agent_workflow.py::test_llm_polish_cannot_replace_refund_safety_notice -q -p no:cacheprovider
```

Expected: tests fail because workflow does not resolve modes or call `llm_client`.

- [ ] **Step 3: Add mode and safety constants**

Edit imports in `backend/app/services/agent_workflow.py`:

```python
import os
```

```python
from app.schemas.agent import (
    AgentAction,
    AgentIntent,
    AgentMode,
    AgentPolicySource,
    AgentProcessRequest,
    AgentProcessResponse,
)
from app.services import llm_client
```

Add constants near `REQUIRED_NODES`:

```python
DEFAULT_AGENT_MODE: AgentMode = "rules"
REFUND_SAFETY_NOTICE = "本流程只给出审核建议，不会真实执行退款，也不会修改支付状态或库存。"
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
```

- [ ] **Step 4: Extend workflow state and initial state**

Update `WorkflowState`:

```python
    mode: AgentMode = DEFAULT_AGENT_MODE
```

Update `_initial_state`:

```python
def _initial_state(request: AgentProcessRequest) -> WorkflowState:
    message = request.message
    return WorkflowState(
        request=request,
        mode=_resolve_agent_mode(request.mode),
        order_number=request.order_number or _find_order_number(message),
        external_id=request.external_id or _find_external_id(message),
        ticket_number=request.ticket_number or _find_ticket_number(message),
    )
```

Add resolver near helper functions:

```python
def _resolve_agent_mode(request_mode: AgentMode | None) -> AgentMode:
    if request_mode is not None:
        return request_mode
    env_mode = os.getenv("AGENT_MODE", DEFAULT_AGENT_MODE).strip().lower()
    return "llm_assisted" if env_mode == "llm_assisted" else "rules"
```

- [ ] **Step 5: Split rule classification and insert guarded LLM assist**

Replace `_intent_classification` with:

```python
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
```

- [ ] **Step 6: Enforce refund safety and guarded polish**

Update `_response_generation` so it generates the same deterministic reply, then optionally polishes:

```python
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
```

Add helpers near reply helpers:

```python
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
```

Update `_refund_reply` to use the constant:

```python
    return (
        f"已完成退款资格检查，当前建议：{recommendation}。原因：{reasons}。"
        f"{REFUND_SAFETY_NOTICE}"
    )
```

- [ ] **Step 7: Run targeted workflow tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_agent_workflow.py -q -p no:cacheprovider
```

Expected: all workflow tests pass.

- [ ] **Step 8: Record changed files**

Record:

```text
Changed: backend/app/services/agent_workflow.py
Changed: backend/tests/test_agent_workflow.py
Verification: workflow tests pass
Git commit skipped because E:\code3\kefuAgent is not a git repository.
```

---

### Task 4: Evaluation Mode Parameter

**Files:**
- Modify: `backend/app/services/evaluation.py`
- Modify: `backend/scripts/run_eval.py`
- Modify: `backend/tests/test_evaluation.py`

**Interfaces:**
- Consumes: `AgentMode`
- Produces: `run_evaluation(session: Session, cases: Sequence[EvaluationCase] | None = None, mode: AgentMode = "rules") -> EvaluationReport`
- Produces: CLI argument `--mode rules|llm_assisted`

- [ ] **Step 1: Write failing evaluation mode test**

Append to `backend/tests/test_evaluation.py`:

```python
def test_run_evaluation_forwards_requested_mode(monkeypatch) -> None:
    captured_modes: list[str | None] = []

    def fake_process_customer_message(_session, request):
        captured_modes.append(request.mode)
        return AgentProcessResponse(
            intent="other",
            reply="ok",
            actions=[
                AgentAction(
                    node="policy_retrieval",
                    tool_name="search_policy",
                    status="success",
                    summary="ok",
                )
            ],
            policy_sources=[
                AgentPolicySource(
                    policy_title="售后政策",
                    source_file="general.md",
                    score=0.9,
                )
            ],
            need_human=False,
            ticket_id=None,
            confidence=0.8,
        )

    monkeypatch.setattr(
        "app.services.evaluation.process_customer_message",
        fake_process_customer_message,
    )
    case = EvaluationCase(
        id="EVAL-MODE-001",
        user_message="你好",
        expected_intent="other",
        expected_tools=["search_policy"],
        expected_need_human=False,
        expected_policy_keywords=["售后"],
    )

    run_evaluation(session=object(), cases=[case], mode="llm_assisted")  # type: ignore[arg-type]

    assert captured_modes == ["llm_assisted"]
```

- [ ] **Step 2: Run the new test and confirm failure**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py::test_run_evaluation_forwards_requested_mode -q -p no:cacheprovider
```

Expected: fails because `run_evaluation` does not accept `mode`.

- [ ] **Step 3: Implement evaluation mode forwarding**

Edit imports in `backend/app/services/evaluation.py`:

```python
from app.schemas.agent import AgentIntent, AgentMode
```

Update function signature and request construction:

```python
def run_evaluation(
    session: Session,
    cases: Sequence[EvaluationCase] | None = None,
    mode: AgentMode = "rules",
) -> EvaluationReport:
```

```python
        response = process_customer_message(
            session,
            AgentProcessRequest(message=case.user_message, mode=mode),
        )
```

- [ ] **Step 4: Add CLI argument**

Edit `backend/scripts/run_eval.py` parser:

```python
    parser.add_argument(
        "--mode",
        choices=["rules", "llm_assisted"],
        default="rules",
        help="Agent processing mode for evaluation. Default keeps the deterministic rules baseline.",
    )
```

Update both `run_evaluation` calls:

```python
                report = run_evaluation(session, cases, mode=args.mode)
```

and:

```python
                    report = run_evaluation(session, cases, mode=args.mode)
```

Update final print:

```python
        "Evaluation completed: "
        f"mode={args.mode}, "
        f"total={report.total_cases}, passed={report.passed_cases}, "
```

- [ ] **Step 5: Run evaluation tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation.py -q -p no:cacheprovider
```

Expected: evaluation tests pass.

- [ ] **Step 6: Record changed files**

Record:

```text
Changed: backend/app/services/evaluation.py
Changed: backend/scripts/run_eval.py
Changed: backend/tests/test_evaluation.py
Verification: evaluation tests pass
Git commit skipped because E:\code3\kefuAgent is not a git repository.
```

---

### Task 5: Front-End Persisted Smart Assist Toggle

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Produces: `export type AgentMode = "rules" | "llm_assisted";`
- Produces: `AgentProcessRequest.mode?: AgentMode;`
- Produces: `SMART_ASSIST_PREF_KEY = "kefu-agent-smart-assist-enabled"`
- Consumes: existing `processAgent(request: AgentProcessRequest)`

- [ ] **Step 1: Add front-end request type**

Edit `frontend/src/types.ts`:

```ts
export type AgentMode = "rules" | "llm_assisted";
```

Update `AgentProcessRequest`:

```ts
export type AgentProcessRequest = {
  message: string;
  order_number?: string;
  external_id?: string;
  ticket_number?: string;
  requested_amount?: string;
  mode?: AgentMode;
};
```

- [ ] **Step 2: Add persisted state helpers**

Edit `frontend/src/App.tsx` near constants:

```ts
const SMART_ASSIST_PREF_KEY = "kefu-agent-smart-assist-enabled";
```

Add helper near `readLastAgentRun`:

```ts
function readSmartAssistPreference(): boolean {
  try {
    return localStorage.getItem(SMART_ASSIST_PREF_KEY) === "true";
  } catch {
    return false;
  }
}
```

- [ ] **Step 3: Add ChatPage state and request mode**

Inside `ChatPage`, add state:

```ts
  const [smartAssistEnabled, setSmartAssistEnabled] = useState(() =>
    readSmartAssistPreference(),
  );
```

Add setter inside `ChatPage`:

```ts
  function updateSmartAssistPreference(enabled: boolean) {
    setSmartAssistEnabled(enabled);
    localStorage.setItem(SMART_ASSIST_PREF_KEY, String(enabled));
  }
```

Update submit payload:

```ts
      const payload = compactRequest({
        ...form,
        mode: smartAssistEnabled ? "llm_assisted" : "rules",
      });
```

- [ ] **Step 4: Add the business-facing toggle UI**

In `ChatPage`, inside the existing `.panel-heading` for "接待用户问题", add:

```tsx
          <label className="assist-toggle">
            <input
              checked={smartAssistEnabled}
              onChange={(event) => updateSmartAssistPreference(event.target.checked)}
              type="checkbox"
            />
            <span className="assist-toggle-track" aria-hidden="true" />
            <span className="assist-toggle-copy">
              <strong>智能增强</strong>
              <small>
                {smartAssistEnabled ? "辅助理解表达并优化回复" : "使用稳定规则处理"}
              </small>
            </span>
          </label>
```

- [ ] **Step 5: Style the toggle**

Append to `frontend/src/styles.css`:

```css
.assist-toggle {
  align-items: center;
  cursor: pointer;
  display: inline-flex;
  gap: 10px;
  min-width: 210px;
  user-select: none;
}

.assist-toggle input {
  height: 1px;
  opacity: 0;
  position: absolute;
  width: 1px;
}

.assist-toggle-track {
  background: #d8dee9;
  border-radius: 999px;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.08);
  flex: 0 0 auto;
  height: 24px;
  position: relative;
  transition: background 0.2s ease;
  width: 44px;
}

.assist-toggle-track::after {
  background: #ffffff;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.24);
  content: "";
  height: 18px;
  left: 3px;
  position: absolute;
  top: 3px;
  transition: transform 0.2s ease;
  width: 18px;
}

.assist-toggle input:checked + .assist-toggle-track {
  background: #2563eb;
}

.assist-toggle input:checked + .assist-toggle-track::after {
  transform: translateX(20px);
}

.assist-toggle-copy {
  display: grid;
  gap: 2px;
  line-height: 1.2;
}

.assist-toggle-copy strong {
  color: #111827;
  font-size: 14px;
}

.assist-toggle-copy small {
  color: #6b7280;
  font-size: 12px;
}
```

- [ ] **Step 6: Run front-end build**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 7: Record changed files**

Record:

```text
Changed: frontend/src/types.ts
Changed: frontend/src/App.tsx
Changed: frontend/src/styles.css
Verification: npm run build passes
Git commit skipped because E:\code3\kefuAgent is not a git repository.
```

---

### Task 6: Documentation Updates

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/demo-guide.md`

**Interfaces:**
- Consumes: implemented env vars `AGENT_MODE`, `DASHSCOPE_API_KEY`, `DASHSCOPE_MODEL`, `DASHSCOPE_BASE_URL`, `DASHSCOPE_TIMEOUT_SECONDS`
- Produces: user-facing setup and demo instructions for rules and smart assist modes.

- [ ] **Step 1: Update README current-version language**

In `README.md`, replace:

```markdown
当前版本不接入 Chat LLM，主流程使用确定性规则状态机，重点展示业务工具调用、RAG 政策检索、安全边界和可观测评测闭环。下一阶段计划加入可选的 LLM-assisted 模式，用于意图理解和客服回复润色，但不让大模型直接执行退款、支付或库存操作。
```

with:

```markdown
当前版本主流程使用确定性规则状态机，并提供可选的 LLM-assisted 智能增强模式。智能增强只辅助非标准表达理解和客服回复润色，不让大模型直接执行退款、支付、库存或工单状态修改。没有 API Key 时默认 `rules` 模式仍可完整运行。
```

- [ ] **Step 2: Add README configuration block**

Under backend startup env vars in `README.md`, add:

```powershell
# 可选：智能增强模式。默认 rules，无 API Key 也能完整运行。
$env:AGENT_MODE = 'rules'
# $env:AGENT_MODE = 'llm_assisted'
# $env:DASHSCOPE_API_KEY = '<your-api-key>'
# $env:DASHSCOPE_MODEL = 'qwen-plus'
```

- [ ] **Step 3: Update README next-stage section**

Replace the "下一阶段" section with:

```markdown
## LLM-assisted 智能增强

项目支持可选 `LLM-assisted` 模式：

- 默认仍是 `rules`，保证无 API Key 可运行。
- 客服处理台提供“智能增强”开关，开关状态保存在浏览器本地。
- 有 API Key 且开启增强时，LLM 只辅助意图理解和回复润色。
- 所有订单、物流、退款资格和政策事实仍来自 PostgreSQL、工具 API 和 Qdrant。
- 退款、支付、库存、工单状态等高风险判断仍由确定性规则和工具校验。
```

- [ ] **Step 4: Update architecture Agent section**

In `docs/architecture.md`, replace the "当前使用规则状态机，不使用 LangGraph，不接 Chat LLM。" sentence with:

```markdown
当前使用规则状态机作为主流程，不使用 LangGraph。第 11 阶段增加了可选 `llm_assisted` 模式，但 LLM 只插入在意图辅助理解和回复润色两个窄接口中。
```

Add:

```markdown
LLM-assisted 模式的数据流：

```text
规则意图识别
  -> 低置信度或 other 时可选 LLM 辅助识别
  -> 规则信息检查、政策检索、工具选择和业务动作
  -> 规则生成回复
  -> 可选 LLM 润色回复
  -> 安全文案和高风险动作校验
```
```

- [ ] **Step 5: Update demo guide**

In `docs/demo-guide.md`, add after backend env vars:

```powershell
# 默认稳定规则模式
$env:AGENT_MODE = 'rules'

# 可选智能增强：需要 API Key；失败会回退 rules
# $env:AGENT_MODE = 'llm_assisted'
# $env:DASHSCOPE_API_KEY = '<your-api-key>'
# $env:DASHSCOPE_MODEL = 'qwen-plus'
```

Add to recommended demo path:

```markdown
### 智能增强开关

页面：客服处理台

演示点：

- 打开“智能增强”后，刷新页面仍保持打开。
- 关闭后同样持久化保持关闭。
- 无 API Key 或调用失败时，系统仍使用稳定规则处理。
- 页面只展示业务文案，不展示模型、API Key、工具名或 JSON。
```

- [ ] **Step 6: Verify markdown has no unresolved planning words**

Run:

```powershell
cd E:\code3\kefuAgent
Select-String -Path README.md,docs\architecture.md,docs\demo-guide.md -Pattern 'TBD|TODO|placeholder|待定|未定' -CaseSensitive:$false
```

Expected: no matches from the new documentation.

- [ ] **Step 7: Record changed files**

Record:

```text
Changed: README.md
Changed: docs/architecture.md
Changed: docs/demo-guide.md
Verification: documentation scan has no unresolved planning words
Git commit skipped because E:\code3\kefuAgent is not a git repository.
```

---

### Task 7: Full Verification

**Files:**
- Read: all changed files from Tasks 1-6
- No planned source modifications unless verification exposes a defect.

**Interfaces:**
- Consumes: all implemented backend, frontend, test, and documentation changes.
- Produces: final verification summary.

- [ ] **Step 1: Run backend targeted tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_llm_client.py tests\test_agent_workflow.py tests\test_evaluation.py -q -p no:cacheprovider
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run full backend tests**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:DATABASE_URL = 'postgresql+psycopg://postgres:123456@localhost:5432/postgres'
$env:QDRANT_URL = 'http://localhost:6333'
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

Expected: all backend tests pass.

- [ ] **Step 3: Run front-end build**

Run:

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

Expected: TypeScript and Vite build pass.

- [ ] **Step 4: Run rules evaluation baseline**

Run:

```powershell
cd E:\code3\kefuAgent\backend
$env:DATABASE_URL = 'postgresql+psycopg://postgres:123456@localhost:5432/postgres'
$env:QDRANT_URL = 'http://localhost:6333'
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
.\.venv\Scripts\python.exe -m scripts.run_eval --mode rules
```

Expected: evaluation completes with the existing rules baseline. If the sandbox blocks report writing to `data/eval/eval_report.json`, report the permission issue and keep the backend tests as the authoritative local verification.

- [ ] **Step 5: Inspect API response shape**

Run:

```powershell
cd E:\code3\kefuAgent\backend
.\.venv\Scripts\python.exe -m pytest tests\test_agent_workflow.py::test_agent_api_returns_required_json_shape -q -p no:cacheprovider
```

Expected: response keys are still exactly:

```text
intent, reply, actions, policy_sources, need_human, ticket_id, confidence
```

- [ ] **Step 6: Prepare final summary**

Summarize:

```text
Implemented optional LLM-assisted mode with rules fallback.
Added persisted front-end 智能增强 toggle.
Kept Agent response shape unchanged.
Kept refund/payment/inventory safety boundaries.
Updated eval CLI with --mode.
Updated README and docs.
Verification commands and outcomes:
- backend tests: ...
- frontend build: ...
- rules eval: ...
```
