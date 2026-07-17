from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.schemas.agent import AgentAction, AgentPolicySource, AgentProcessResponse
from app.schemas.evaluation import (
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationLatencyPercentiles,
    EvaluationMetrics,
    EvaluationReport,
)
from app.services.evaluation import (
    DEFAULT_EVAL_CASES_PATH,
    DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH,
    DEFAULT_EVAL_MARKDOWN_PATH,
    DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH,
    DEFAULT_EVAL_REPORT_PATH,
    compute_failure_reason_counts,
    compute_latency_percentiles,
    compute_metrics,
    compute_metrics_by_intent,
    evaluate_agent_response,
    load_eval_cases,
    read_eval_comparison,
    read_latest_eval_report,
    run_evaluation,
    write_evaluation_reports,
)
from app.services.admin_auth import authenticate_admin, create_admin_user
from scripts.run_eval import resolve_report_paths


ALLOWED_INTENTS = {
    "refund_request",
    "shipping_issue",
    "invoice_request",
    "account_issue",
    "complaint",
    "other",
}

ALLOWED_TOOLS = {
    "search_policy",
    "get_order_info",
    "check_refund_eligibility",
    "create_ticket",
    "escalate_to_human",
}


def test_eval_case_file_contains_50_complete_cases() -> None:
    cases = load_eval_cases(DEFAULT_EVAL_CASES_PATH)

    assert len(cases) == 50
    assert len({case.id for case in cases}) == 50

    counts = {intent: 0 for intent in ALLOWED_INTENTS}
    for case in cases:
        assert case.id.startswith("EVAL-")
        assert case.user_message
        assert case.expected_intent in ALLOWED_INTENTS
        assert set(case.expected_tools).issubset(ALLOWED_TOOLS)
        assert isinstance(case.expected_need_human, bool)
        assert case.expected_policy_keywords
        counts[case.expected_intent] += 1

    assert counts["refund_request"] >= 12
    assert counts["shipping_issue"] >= 8
    assert counts["invoice_request"] >= 7
    assert counts["complaint"] >= 8
    assert counts["account_issue"] >= 5
    assert counts["other"] >= 5
    assert any("ORD-2026-" in case.user_message for case in cases)
    assert any("U000" in case.user_message for case in cases)
    assert any("TCK-2026-" in case.user_message for case in cases)
    assert any(case.expected_need_human for case in cases)
    assert any(not case.expected_need_human for case in cases)
    assert any(
        case.expected_intent == "refund_request" and not case.expected_need_human
        for case in cases
    )


def test_evaluate_agent_response_scores_tools_policy_and_failures() -> None:
    case = EvaluationCase(
        id="EVAL-TEST-001",
        user_message="ORD-2026-0002 商品坏了我要退款",
        expected_intent="refund_request",
        expected_tools=[
            "search_policy",
            "get_order_info",
            "check_refund_eligibility",
        ],
        expected_need_human=False,
        expected_policy_keywords=["七天无理由"],
    )
    response = AgentProcessResponse(
        intent="refund_request",
        reply="已完成退款资格检查",
        actions=[
            AgentAction(
                node="policy_retrieval",
                tool_name="search_policy",
                status="success",
                summary="ok",
            ),
            AgentAction(
                node="business_action",
                tool_name="get_order_info",
                status="success",
                summary="ok",
            ),
            AgentAction(
                node="business_action",
                tool_name="get_order_info",
                status="success",
                summary="duplicate ignored",
            ),
            AgentAction(
                node="business_action",
                tool_name="check_refund_eligibility",
                status="success",
                summary="ok",
            ),
        ],
        policy_sources=[
            AgentPolicySource(
                policy_title="七天无理由退货规则",
                source_file="seven_day_return.md",
                score=0.91,
            )
        ],
        need_human=False,
        ticket_id=None,
        confidence=0.9,
    )

    result = evaluate_agent_response(case, response, latency_ms=12.34)

    assert result.passed is True
    assert result.failure_reasons == []
    assert result.actual_tools == [
        "search_policy",
        "get_order_info",
        "check_refund_eligibility",
    ]
    assert result.actual_policy_sources[0].policy_title == "七天无理由退货规则"

    failed_response = response.model_copy(
        update={
            "intent": "other",
            "actions": [
                AgentAction(
                    node="policy_retrieval",
                    tool_name="search_policy",
                    status="success",
                    summary="ok",
                )
            ],
            "policy_sources": [
                AgentPolicySource(
                    policy_title="退款到账时间说明",
                    source_file="refund_arrival_time.md",
                    score=0.88,
                )
            ],
            "need_human": True,
        }
    )

    failed_result = evaluate_agent_response(case, failed_response, latency_ms=20.0)

    assert failed_result.passed is False
    assert failed_result.failure_reasons == [
        "intent mismatch: expected refund_request, got other",
        (
            "tools mismatch: expected "
            "['check_refund_eligibility', 'get_order_info', 'search_policy'], "
            "got ['search_policy']"
        ),
        "need_human mismatch: expected False, got True",
        "policy miss: expected one of ['七天无理由'] in policy title/source_file",
    ]


def test_compute_metrics_uses_exact_tool_sets_and_policy_hits() -> None:
    passed = EvaluationCaseResult(
        id="EVAL-TEST-001",
        user_message="case one",
        expected_intent="refund_request",
        actual_intent="refund_request",
        expected_tools=["search_policy", "get_order_info"],
        actual_tools=["get_order_info", "search_policy"],
        expected_need_human=False,
        actual_need_human=False,
        expected_policy_keywords=["七天无理由"],
        actual_policy_sources=[
            AgentPolicySource(
                policy_title="七天无理由退货规则",
                source_file="seven_day_return.md",
                score=0.9,
            )
        ],
        latency_ms=10.0,
        reply="ok",
        actions=[],
        passed=True,
        failure_reasons=[],
        policy_hit=True,
    )
    failed = EvaluationCaseResult(
        id="EVAL-TEST-002",
        user_message="case two",
        expected_intent="complaint",
        actual_intent="other",
        expected_tools=["search_policy", "escalate_to_human"],
        actual_tools=["search_policy"],
        expected_need_human=True,
        actual_need_human=False,
        expected_policy_keywords=["投诉升级"],
        actual_policy_sources=[],
        latency_ms=30.0,
        reply="no",
        actions=[],
        passed=False,
        failure_reasons=["bad"],
        policy_hit=False,
    )

    metrics = compute_metrics([passed, failed])

    assert metrics.intent_accuracy == pytest.approx(0.5)
    assert metrics.tool_call_accuracy == pytest.approx(0.5)
    assert metrics.policy_hit_rate == pytest.approx(0.5)
    assert metrics.human_escalation_accuracy == pytest.approx(0.5)
    assert metrics.average_latency_ms == pytest.approx(20.0)
    assert metrics.auto_resolution_rate == pytest.approx(1.0)


def test_compute_observability_breakdowns_by_intent_latency_and_failure_reason() -> None:
    results = [
        EvaluationCaseResult(
            id="EVAL-TEST-001",
            user_message="refund pass",
            expected_intent="refund_request",
            actual_intent="refund_request",
            expected_tools=["search_policy"],
            actual_tools=["search_policy"],
            expected_need_human=False,
            actual_need_human=False,
            expected_policy_keywords=["七天无理由"],
            actual_policy_sources=[],
            latency_ms=10.0,
            reply="ok",
            actions=[],
            passed=True,
            failure_reasons=[],
            policy_hit=True,
        ),
        EvaluationCaseResult(
            id="EVAL-TEST-002",
            user_message="refund fail",
            expected_intent="refund_request",
            actual_intent="other",
            expected_tools=["search_policy"],
            actual_tools=["search_policy"],
            expected_need_human=False,
            actual_need_human=False,
            expected_policy_keywords=["七天无理由"],
            actual_policy_sources=[],
            latency_ms=20.0,
            reply="no",
            actions=[],
            passed=False,
            failure_reasons=[
                "intent mismatch: expected refund_request, got other",
                "policy miss: expected one of ['七天无理由'] in policy title/source_file",
            ],
            policy_hit=False,
        ),
        EvaluationCaseResult(
            id="EVAL-TEST-003",
            user_message="complaint fail",
            expected_intent="complaint",
            actual_intent="complaint",
            expected_tools=["search_policy", "escalate_to_human"],
            actual_tools=["search_policy"],
            expected_need_human=True,
            actual_need_human=False,
            expected_policy_keywords=["投诉升级"],
            actual_policy_sources=[],
            latency_ms=30.0,
            reply="no",
            actions=[],
            passed=False,
            failure_reasons=[
                (
                    "tools mismatch: expected "
                    "['escalate_to_human', 'search_policy'], got ['search_policy']"
                ),
                "need_human mismatch: expected True, got False",
            ],
            policy_hit=True,
        ),
        EvaluationCaseResult(
            id="EVAL-TEST-004",
            user_message="account pass",
            expected_intent="account_issue",
            actual_intent="account_issue",
            expected_tools=["search_policy"],
            actual_tools=["search_policy"],
            expected_need_human=True,
            actual_need_human=True,
            expected_policy_keywords=["会员售后"],
            actual_policy_sources=[],
            latency_ms=40.0,
            reply="ok",
            actions=[],
            passed=True,
            failure_reasons=[],
            policy_hit=True,
        ),
    ]

    metrics_by_intent = compute_metrics_by_intent(results)
    latency_percentiles = compute_latency_percentiles(results)
    failure_reason_counts = compute_failure_reason_counts(results)

    assert metrics_by_intent["refund_request"].total_cases == 2
    assert metrics_by_intent["refund_request"].passed_cases == 1
    assert metrics_by_intent["refund_request"].metrics.intent_accuracy == pytest.approx(0.5)
    assert metrics_by_intent["complaint"].failed_cases == 1
    assert latency_percentiles.p50_ms == pytest.approx(20.0)
    assert latency_percentiles.p95_ms == pytest.approx(40.0)
    assert latency_percentiles.max_ms == pytest.approx(40.0)
    assert failure_reason_counts == {
        "intent_mismatch": 1,
        "policy_miss": 1,
        "tool_mismatch": 1,
        "human_escalation_mismatch": 1,
    }


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


GENERATED_TEST_DIR = Path(__file__).resolve().parent / "_generated"


def test_write_evaluation_reports_outputs_json_and_markdown() -> None:
    result = EvaluationCaseResult(
        id="EVAL-TEST-001",
        user_message="ORD-2026-0002 商品坏了我要退款",
        expected_intent="refund_request",
        actual_intent="refund_request",
        expected_tools=["search_policy"],
        actual_tools=["search_policy"],
        expected_need_human=False,
        actual_need_human=False,
        expected_policy_keywords=["七天无理由"],
        actual_policy_sources=[
            AgentPolicySource(
                policy_title="七天无理由退货规则",
                source_file="seven_day_return.md",
                score=0.91,
            )
        ],
        latency_ms=14.0,
        reply="ok",
        actions=[],
        passed=True,
        failure_reasons=[],
        policy_hit=True,
    )
    report = EvaluationReport(
        generated_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        metrics=EvaluationMetrics(
            intent_accuracy=1.0,
            tool_call_accuracy=1.0,
            policy_hit_rate=1.0,
            human_escalation_accuracy=1.0,
            average_latency_ms=14.0,
            auto_resolution_rate=1.0,
        ),
        results=[result],
    )
    GENERATED_TEST_DIR.mkdir(exist_ok=True)
    json_path = GENERATED_TEST_DIR / "eval_report_test.json"
    markdown_path = GENERATED_TEST_DIR / "eval_report_test.md"

    write_evaluation_reports(report, json_path=json_path, markdown_path=markdown_path)

    assert json_path.read_text(encoding="utf-8").startswith("{")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# 客服 Agent 评测报告" in markdown
    assert "tool_call_accuracy" in markdown
    assert "无失败案例" in markdown


def test_write_evaluation_reports_can_save_timestamped_history() -> None:
    report = EvaluationReport(
        generated_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
        total_cases=0,
        passed_cases=0,
        failed_cases=0,
        metrics=EvaluationMetrics(
            intent_accuracy=0.0,
            tool_call_accuracy=0.0,
            policy_hit_rate=0.0,
            human_escalation_accuracy=0.0,
            average_latency_ms=0.0,
            auto_resolution_rate=0.0,
        ),
        results=[],
    )
    GENERATED_TEST_DIR.mkdir(exist_ok=True)
    json_path = GENERATED_TEST_DIR / "eval_report_history_latest.json"
    markdown_path = GENERATED_TEST_DIR / "eval_report_history_latest.md"
    history_dir = GENERATED_TEST_DIR / "history"

    write_evaluation_reports(
        report,
        json_path=json_path,
        markdown_path=markdown_path,
        history_dir=history_dir,
        write_history=True,
    )

    history_path = history_dir / "eval_report_20260716_120000.json"
    assert history_path.exists()
    assert history_path.read_text(encoding="utf-8").startswith("{")


def test_run_eval_default_report_paths_keep_rules_baseline_and_separate_llm() -> None:
    rules_json, rules_markdown = resolve_report_paths(
        mode="rules",
        json_report=None,
        markdown_report=None,
    )
    llm_json, llm_markdown = resolve_report_paths(
        mode="llm_assisted",
        json_report=None,
        markdown_report=None,
    )
    explicit_json, explicit_markdown = resolve_report_paths(
        mode="llm_assisted",
        json_report="custom/llm.json",
        markdown_report="custom/llm.md",
    )

    assert rules_json == DEFAULT_EVAL_REPORT_PATH
    assert rules_markdown == DEFAULT_EVAL_MARKDOWN_PATH
    assert llm_json == DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH
    assert llm_markdown == DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH
    assert explicit_json == Path("custom/llm.json")
    assert explicit_markdown == Path("custom/llm.md")


def test_latest_eval_api_returns_metrics_and_failed_case_summary(
    tools_client: TestClient,
    monkeypatch,
) -> None:
    failed = EvaluationCaseResult(
        id="EVAL-TEST-002",
        user_message="我要投诉",
        expected_intent="complaint",
        actual_intent="other",
        expected_tools=["search_policy", "escalate_to_human"],
        actual_tools=["search_policy"],
        expected_need_human=True,
        actual_need_human=False,
        expected_policy_keywords=["投诉升级"],
        actual_policy_sources=[],
        latency_ms=22.0,
        reply="no",
        actions=[],
        passed=False,
        failure_reasons=["intent mismatch: expected complaint, got other"],
        policy_hit=False,
    )
    report = EvaluationReport(
        generated_at=datetime(2026, 7, 16, 12, 30, tzinfo=UTC),
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        metrics=EvaluationMetrics(
            intent_accuracy=0.5,
            tool_call_accuracy=0.5,
            policy_hit_rate=0.5,
            human_escalation_accuracy=0.5,
            average_latency_ms=20.0,
            auto_resolution_rate=0.5,
        ),
        metrics_by_intent={
            "complaint": {
                "total_cases": 1,
                "passed_cases": 0,
                "failed_cases": 1,
                "metrics": {
                    "intent_accuracy": 0.0,
                    "tool_call_accuracy": 0.0,
                    "policy_hit_rate": 0.0,
                    "human_escalation_accuracy": 0.0,
                    "average_latency_ms": 22.0,
                    "auto_resolution_rate": 1.0,
                },
            }
        },
        latency_percentiles={"p50_ms": 22.0, "p95_ms": 22.0, "max_ms": 22.0},
        failure_reason_counts={"intent_mismatch": 1},
        results=[failed],
    )
    GENERATED_TEST_DIR.mkdir(exist_ok=True)
    report_path = GENERATED_TEST_DIR / "latest_eval_report_test.json"
    report_path.write_text(report.model_dump_json(), encoding="utf-8")
    monkeypatch.setattr(
        "app.services.evaluation.DEFAULT_EVAL_REPORT_PATH",
        report_path,
    )

    response = tools_client.get("/api/eval/latest")

    assert response.status_code == 200
    data = response.json()
    assert data["generated_at"] == "2026-07-16T12:30:00Z"
    assert data["total_cases"] == 2
    assert data["passed_cases"] == 1
    assert data["failed_cases_count"] == 1
    assert data["metrics"]["intent_accuracy"] == 0.5
    assert data["metrics_by_intent"]["complaint"]["failed_cases"] == 1
    assert data["latency_percentiles"]["p95_ms"] == 22.0
    assert data["failure_reason_counts"] == {"intent_mismatch": 1}
    assert len(data["failed_cases"]) == 1
    assert data["failed_cases"][0]["id"] == "EVAL-TEST-002"


def test_eval_history_api_returns_recent_report_summaries(
    tools_client: TestClient,
    monkeypatch,
) -> None:
    history_dir = GENERATED_TEST_DIR / "api_history"
    history_dir.mkdir(parents=True, exist_ok=True)

    older = EvaluationReport(
        generated_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
        total_cases=2,
        passed_cases=1,
        failed_cases=1,
        metrics=EvaluationMetrics(
            intent_accuracy=0.5,
            tool_call_accuracy=0.5,
            policy_hit_rate=0.5,
            human_escalation_accuracy=0.5,
            average_latency_ms=30.0,
            auto_resolution_rate=0.5,
        ),
        latency_percentiles=EvaluationLatencyPercentiles(
            p50_ms=30.0,
            p95_ms=30.0,
            max_ms=30.0,
        ),
        failure_reason_counts={"policy_miss": 1},
        results=[],
    )
    newer = older.model_copy(
        update={
            "generated_at": datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
            "passed_cases": 2,
            "failed_cases": 0,
            "metrics": EvaluationMetrics(
                intent_accuracy=1.0,
                tool_call_accuracy=1.0,
                policy_hit_rate=1.0,
                human_escalation_accuracy=1.0,
                average_latency_ms=20.0,
                auto_resolution_rate=0.5,
            ),
            "latency_percentiles": EvaluationLatencyPercentiles(
                p50_ms=20.0,
                p95_ms=20.0,
                max_ms=20.0,
            ),
            "failure_reason_counts": {},
        }
    )
    (history_dir / "eval_report_20260716_110000.json").write_text(
        older.model_dump_json(),
        encoding="utf-8",
    )
    (history_dir / "eval_report_20260716_120000.json").write_text(
        newer.model_dump_json(),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.evaluation.DEFAULT_EVAL_HISTORY_DIR",
        history_dir,
    )

    response = tools_client.get("/api/eval/history?limit=1")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["reports"]) == 1
    assert data["reports"][0]["report_file"] == "eval_report_20260716_120000.json"
    assert data["reports"][0]["passed_cases"] == 2
    assert data["reports"][0]["latency_percentiles"]["p50_ms"] == 20.0


def test_legacy_eval_report_without_mode_still_reads() -> None:
    result = _comparison_result(
        case_id="EVAL-LEGACY-001",
        expected_intent="refund_request",
        actual_intent="refund_request",
        passed=True,
        failure_reasons=[],
        latency_ms=12.0,
    )
    report = _comparison_report(
        generated_at=datetime(2026, 7, 16, 13, 0, tzinfo=UTC),
        results=[result],
    )
    payload = report.model_dump(mode="json")
    payload.pop("mode", None)

    GENERATED_TEST_DIR.mkdir(exist_ok=True)
    report_path = GENERATED_TEST_DIR / "legacy_eval_report.json"
    report_path.write_text(
        __import__("json").dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    latest = read_latest_eval_report(report_path)

    assert latest.mode is None
    assert latest.total_cases == 1
    assert latest.failed_cases_count == 0


def test_read_eval_comparison_calculates_metric_intent_and_failure_diffs() -> None:
    rules_results = [
        _comparison_result(
            case_id="EVAL-DIFF-001",
            expected_intent="refund_request",
            actual_intent="other",
            passed=False,
            failure_reasons=["intent mismatch: expected refund_request, got other"],
            latency_ms=10.0,
        ),
        _comparison_result(
            case_id="EVAL-DIFF-002",
            expected_intent="shipping_issue",
            actual_intent="shipping_issue",
            passed=True,
            failure_reasons=[],
            latency_ms=20.0,
        ),
        _comparison_result(
            case_id="EVAL-DIFF-003",
            expected_intent="complaint",
            actual_intent="other",
            passed=False,
            failure_reasons=["intent mismatch: expected complaint, got other"],
            latency_ms=30.0,
        ),
        _comparison_result(
            case_id="EVAL-DIFF-004",
            expected_intent="account_issue",
            actual_intent="account_issue",
            passed=True,
            failure_reasons=[],
            latency_ms=40.0,
        ),
    ]
    llm_results = [
        _comparison_result(
            case_id="EVAL-DIFF-001",
            expected_intent="refund_request",
            actual_intent="refund_request",
            passed=True,
            failure_reasons=[],
            latency_ms=15.0,
        ),
        _comparison_result(
            case_id="EVAL-DIFF-002",
            expected_intent="shipping_issue",
            actual_intent="other",
            passed=False,
            failure_reasons=["intent mismatch: expected shipping_issue, got other"],
            latency_ms=25.0,
        ),
        _comparison_result(
            case_id="EVAL-DIFF-003",
            expected_intent="complaint",
            actual_intent="other",
            passed=False,
            failure_reasons=["intent mismatch: expected complaint, got other"],
            latency_ms=35.0,
        ),
        _comparison_result(
            case_id="EVAL-DIFF-004",
            expected_intent="account_issue",
            actual_intent="account_issue",
            passed=True,
            failure_reasons=[],
            latency_ms=45.0,
        ),
    ]
    rules_report = _comparison_report(
        generated_at=datetime(2026, 7, 16, 13, 10, tzinfo=UTC),
        results=rules_results,
        mode="rules",
    )
    llm_report = _comparison_report(
        generated_at=datetime(2026, 7, 16, 13, 20, tzinfo=UTC),
        results=llm_results,
        mode="llm_assisted",
    )
    GENERATED_TEST_DIR.mkdir(exist_ok=True)
    rules_path = GENERATED_TEST_DIR / "eval_report_rules_compare.json"
    llm_path = GENERATED_TEST_DIR / "eval_report_llm_compare.json"
    rules_path.write_text(rules_report.model_dump_json(), encoding="utf-8")
    llm_path.write_text(llm_report.model_dump_json(), encoding="utf-8")

    comparison = read_eval_comparison(rules_path=rules_path, llm_path=llm_path)

    assert comparison.rules_report is not None
    assert comparison.rules_report.mode == "rules"
    assert comparison.llm_assisted_report is not None
    assert comparison.llm_assisted_report.mode == "llm_assisted"
    assert comparison.diff_summary.metric_deltas["average_latency_ms"] == pytest.approx(5.0)
    assert comparison.diff_summary.metric_deltas["passed_cases"] == pytest.approx(0.0)
    assert comparison.diff_summary.intent_deltas["refund_request"]["intent_accuracy"] == pytest.approx(1.0)
    assert comparison.diff_summary.intent_deltas["shipping_issue"]["intent_accuracy"] == pytest.approx(-1.0)
    assert [item.id for item in comparison.diff_summary.rules_failed_llm_passed] == [
        "EVAL-DIFF-001"
    ]
    assert [item.id for item in comparison.diff_summary.llm_failed_rules_passed] == [
        "EVAL-DIFF-002"
    ]
    assert [item.id for item in comparison.diff_summary.both_failed] == [
        "EVAL-DIFF-003"
    ]


def test_read_eval_comparison_returns_empty_llm_state_without_key(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    report = _comparison_report(
        generated_at=datetime(2026, 7, 16, 13, 30, tzinfo=UTC),
        results=[
            _comparison_result(
                case_id="EVAL-MISSING-001",
                expected_intent="other",
                actual_intent="other",
                passed=True,
                failure_reasons=[],
                latency_ms=9.0,
            )
        ],
        mode="rules",
    )
    GENERATED_TEST_DIR.mkdir(exist_ok=True)
    rules_path = GENERATED_TEST_DIR / "eval_report_rules_only.json"
    missing_llm_path = GENERATED_TEST_DIR / "eval_report_llm_missing.json"
    rules_path.write_text(report.model_dump_json(), encoding="utf-8")
    if missing_llm_path.exists():
        missing_llm_path.unlink()

    comparison = read_eval_comparison(rules_path=rules_path, llm_path=missing_llm_path)

    assert comparison.rules_report is not None
    assert comparison.llm_assisted_report is None
    assert comparison.diff_summary.metric_deltas == {}
    assert comparison.llm_status.configured is False
    assert comparison.llm_status.fallback_likely is True
    assert "未连接模型或已回退" in comparison.llm_status.message


def test_admin_eval_compare_api_requires_login(tools_client: TestClient) -> None:
    response = tools_client.get("/api/admin/eval/compare")

    assert response.status_code == 401


def test_admin_eval_compare_api_returns_empty_llm_report(
    tools_client: TestClient,
    tools_db_session,
    monkeypatch,
) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    create_admin_user(
        tools_db_session,
        username="stage15-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage15-admin",
        password="correct-password",
    )
    assert login is not None

    report = _comparison_report(
        generated_at=datetime(2026, 7, 16, 13, 40, tzinfo=UTC),
        results=[
            _comparison_result(
                case_id="EVAL-API-001",
                expected_intent="other",
                actual_intent="other",
                passed=True,
                failure_reasons=[],
                latency_ms=11.0,
            )
        ],
        mode="rules",
    )
    GENERATED_TEST_DIR.mkdir(exist_ok=True)
    rules_path = GENERATED_TEST_DIR / "eval_report_admin_rules.json"
    llm_path = GENERATED_TEST_DIR / "eval_report_admin_llm_missing.json"
    history_dir = GENERATED_TEST_DIR / "history_admin_llm_missing_uncreated"
    rules_path.write_text(report.model_dump_json(), encoding="utf-8")
    if llm_path.exists():
        llm_path.unlink()
    monkeypatch.setattr("app.services.evaluation.DEFAULT_EVAL_REPORT_RULES_PATH", rules_path)
    monkeypatch.setattr("app.services.evaluation.DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH", llm_path)
    monkeypatch.setattr("app.services.evaluation.DEFAULT_EVAL_HISTORY_DIR", history_dir)

    response = tools_client.get(
        "/api/admin/eval/compare",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["rules_report"]["total_cases"] == 1
    assert data["llm_assisted_report"] is None
    assert data["diff_summary"]["metric_deltas"] == {}
    assert data["llm_status"]["configured"] is False


def test_llm_assisted_eval_job_status_schema_serializes_safe_fields() -> None:
    from app.schemas.evaluation import LlmAssistedEvaluationJobStatus

    status = LlmAssistedEvaluationJobStatus(
        status="running",
        message="增强模式评测正在生成，请稍后查看。",
        started_at=datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
        finished_at=None,
        report_generated_at=None,
    )

    assert status.model_dump(mode="json") == {
        "status": "running",
        "message": "增强模式评测正在生成，请稍后查看。",
        "started_at": "2026-07-16T15:00:00Z",
        "finished_at": None,
        "report_generated_at": None,
    }


def test_llm_assisted_eval_job_rejects_missing_api_key(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with pytest.raises(evaluation_jobs.EvaluationJobError) as error:
        evaluation_jobs.start_llm_assisted_evaluation_job()

    assert "DASHSCOPE_API_KEY" in str(error.value)
    assert evaluation_jobs.get_llm_assisted_evaluation_status().status == "idle"


def test_llm_assisted_eval_job_allows_only_one_running_job(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    first = evaluation_jobs.start_llm_assisted_evaluation_job()
    second = evaluation_jobs.start_llm_assisted_evaluation_job()

    assert first.started is True
    assert first.status.status == "running"
    assert second.started is False
    assert second.status.status == "running"


def test_llm_assisted_eval_job_records_success(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    generated_at = datetime(2026, 7, 16, 15, 30, tzinfo=UTC)

    class FakeReport:
        def __init__(self) -> None:
            self.generated_at = generated_at

    monkeypatch.setattr(
        evaluation_jobs,
        "_execute_llm_assisted_evaluation",
        lambda: FakeReport(),
    )

    start = evaluation_jobs.start_llm_assisted_evaluation_job()
    evaluation_jobs.run_llm_assisted_evaluation_job()
    status = evaluation_jobs.get_llm_assisted_evaluation_status()

    assert start.started is True
    assert status.status == "succeeded"
    assert status.report_generated_at == generated_at
    assert "已生成" in status.message


def test_llm_assisted_eval_job_records_safe_failure(monkeypatch) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    def fail() -> None:
        raise RuntimeError("provider payload with secret")

    monkeypatch.setattr(evaluation_jobs, "_execute_llm_assisted_evaluation", fail)

    evaluation_jobs.start_llm_assisted_evaluation_job()
    evaluation_jobs.run_llm_assisted_evaluation_job()
    status = evaluation_jobs.get_llm_assisted_evaluation_status()

    assert status.status == "failed"
    assert "生成失败" in status.message
    assert "secret" not in status.message


def test_admin_llm_eval_run_requires_login(tools_client: TestClient) -> None:
    response = tools_client.post("/api/admin/eval/llm-assisted/run")

    assert response.status_code == 401


def test_admin_llm_eval_status_requires_login(tools_client: TestClient) -> None:
    response = tools_client.get("/api/admin/eval/llm-assisted/status")

    assert response.status_code == 401


def test_admin_llm_eval_run_reports_missing_key(
    tools_client: TestClient,
    tools_db_session,
    monkeypatch,
) -> None:
    from app.services import evaluation_jobs

    evaluation_jobs.reset_llm_assisted_evaluation_job_for_tests()
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    create_admin_user(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    assert login is not None

    response = tools_client.post(
        "/api/admin/eval/llm-assisted/run",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 400
    assert "DASHSCOPE_API_KEY" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_admin_llm_eval_run_starts_background_job(
    tools_client: TestClient,
    tools_db_session,
    monkeypatch,
) -> None:
    from app.schemas.evaluation import LlmAssistedEvaluationJobStatus
    from app.services.evaluation_jobs import EvaluationJobStartResult

    create_admin_user(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    assert login is not None
    calls: list[str] = []

    def fake_start() -> EvaluationJobStartResult:
        return EvaluationJobStartResult(
            status=LlmAssistedEvaluationJobStatus(
                status="running",
                message="增强模式评测正在生成，请稍后查看。",
                started_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
            ),
            started=True,
        )

    def fake_run() -> None:
        calls.append("run")

    monkeypatch.setattr(
        "app.api.admin.evaluation_jobs.start_llm_assisted_evaluation_job",
        fake_start,
    )
    monkeypatch.setattr(
        "app.api.admin.evaluation_jobs.run_llm_assisted_evaluation_job",
        fake_run,
    )

    response = tools_client.post(
        "/api/admin/eval/llm-assisted/run",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert calls == ["run"]


def test_admin_llm_eval_status_returns_current_job(
    tools_client: TestClient,
    tools_db_session,
    monkeypatch,
) -> None:
    from app.schemas.evaluation import LlmAssistedEvaluationJobStatus

    create_admin_user(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    login = authenticate_admin(
        tools_db_session,
        username="stage16-admin",
        password="correct-password",
    )
    assert login is not None

    monkeypatch.setattr(
        "app.api.admin.evaluation_jobs.get_llm_assisted_evaluation_status",
        lambda: LlmAssistedEvaluationJobStatus(
            status="succeeded",
            message="增强模式评测已生成，正在刷新对比结果。",
            started_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
            finished_at=datetime(2026, 7, 16, 16, 2, tzinfo=UTC),
            report_generated_at=datetime(2026, 7, 16, 16, 2, tzinfo=UTC),
        ),
    )

    response = tools_client.get(
        "/api/admin/eval/llm-assisted/status",
        headers={"Authorization": f"Bearer {login.token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert "已生成" in response.json()["message"]


def _comparison_result(
    *,
    case_id: str,
    expected_intent: str,
    actual_intent: str,
    passed: bool,
    failure_reasons: list[str],
    latency_ms: float,
) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        id=case_id,
        user_message=f"{case_id} 用户问题",
        expected_intent=expected_intent,  # type: ignore[arg-type]
        actual_intent=actual_intent,  # type: ignore[arg-type]
        expected_tools=["search_policy"],
        actual_tools=["search_policy"],
        expected_need_human=False,
        actual_need_human=False,
        expected_policy_keywords=["售后"],
        actual_policy_sources=[
            AgentPolicySource(
                policy_title="售后政策",
                source_file="general.md",
                score=0.9,
            )
        ],
        latency_ms=latency_ms,
        reply="ok",
        actions=[],
        passed=passed,
        failure_reasons=failure_reasons,
        policy_hit=True,
    )


def _comparison_report(
    *,
    generated_at: datetime,
    results: list[EvaluationCaseResult],
    mode: str | None = None,
) -> EvaluationReport:
    passed_cases = sum(1 for result in results if result.passed)
    return EvaluationReport(
        generated_at=generated_at,
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        metrics=compute_metrics(results),
        metrics_by_intent=compute_metrics_by_intent(results),
        latency_percentiles=compute_latency_percentiles(results),
        failure_reason_counts=compute_failure_reason_counts(results),
        results=results,
        mode=mode,  # type: ignore[arg-type]
    )
