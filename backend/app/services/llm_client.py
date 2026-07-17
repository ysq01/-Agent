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
