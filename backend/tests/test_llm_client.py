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
