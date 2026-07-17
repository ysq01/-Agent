from __future__ import annotations

import json
import math
import os
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.schemas.agent import AgentIntent, AgentMode
from app.schemas.agent import AgentProcessRequest, AgentProcessResponse
from app.schemas.evaluation import (
    EvaluationCase,
    EvaluationCompareResponse,
    EvaluationComparisonCase,
    EvaluationDiffSummary,
    EvaluationCaseResult,
    EvaluationHistoryItem,
    EvaluationHistoryResponse,
    EvaluationIntentMetrics,
    EvaluationLatencyPercentiles,
    EvaluationLlmStatus,
    EvaluationMetrics,
    EvaluationReport,
    EvaluationReportSummary,
    LatestEvaluationResponse,
)
from app.services.agent_workflow import process_customer_message


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVAL_DIR = PROJECT_ROOT / "data" / "eval"
DEFAULT_EVAL_CASES_PATH = DEFAULT_EVAL_DIR / "customer_service_eval_cases.jsonl"
DEFAULT_EVAL_REPORT_PATH = DEFAULT_EVAL_DIR / "eval_report.json"
DEFAULT_EVAL_REPORT_RULES_PATH = DEFAULT_EVAL_DIR / "eval_report_rules.json"
DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH = (
    DEFAULT_EVAL_DIR / "eval_report_llm_assisted.json"
)
DEFAULT_EVAL_MARKDOWN_PATH = DEFAULT_EVAL_DIR / "eval_report.md"
DEFAULT_EVAL_MARKDOWN_RULES_PATH = DEFAULT_EVAL_DIR / "eval_report_rules.md"
DEFAULT_EVAL_MARKDOWN_LLM_ASSISTED_PATH = (
    DEFAULT_EVAL_DIR / "eval_report_llm_assisted.md"
)
DEFAULT_EVAL_HISTORY_DIR = DEFAULT_EVAL_DIR / "history"

COMPARISON_METRIC_NAMES = [
    "intent_accuracy",
    "tool_call_accuracy",
    "policy_hit_rate",
    "human_escalation_accuracy",
    "auto_resolution_rate",
    "average_latency_ms",
    "p50_ms",
    "p95_ms",
    "max_ms",
    "total_cases",
    "passed_cases",
    "failed_cases_count",
]


def load_eval_cases(path: Path | None = None) -> list[EvaluationCase]:
    cases_path = path or DEFAULT_EVAL_CASES_PATH
    if not cases_path.exists():
        raise FileNotFoundError(f"Evaluation case file not found: {cases_path}")

    if cases_path.suffix.lower() == ".json":
        raw_cases = json.loads(cases_path.read_text(encoding="utf-8"))
        if not isinstance(raw_cases, list):
            raise ValueError("Evaluation JSON file must contain a list of cases.")
        return [EvaluationCase.model_validate(item) for item in raw_cases]

    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(cases_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            cases.append(EvaluationCase.model_validate_json(stripped))
        except ValueError as error:
            raise ValueError(
                f"Invalid evaluation case JSON on line {line_number}: {error}"
            ) from error

    return cases


def run_evaluation(
    session: Session,
    cases: Sequence[EvaluationCase] | None = None,
    mode: AgentMode = "rules",
) -> EvaluationReport:
    eval_cases = list(cases) if cases is not None else load_eval_cases()
    results: list[EvaluationCaseResult] = []

    for case in eval_cases:
        started = time.perf_counter()
        response = process_customer_message(
            session,
            AgentProcessRequest(message=case.user_message, mode=mode),
        )
        latency_ms = (time.perf_counter() - started) * 1000
        results.append(evaluate_agent_response(case, response, latency_ms))

    passed_cases = sum(1 for result in results if result.passed)
    llm_configured = _is_llm_configured()
    return EvaluationReport(
        mode=mode,
        llm_available=llm_configured if mode == "llm_assisted" else None,
        llm_fallback=(not llm_configured) if mode == "llm_assisted" else None,
        generated_at=datetime.now(UTC),
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        metrics=compute_metrics(results),
        metrics_by_intent=compute_metrics_by_intent(results),
        latency_percentiles=compute_latency_percentiles(results),
        failure_reason_counts=compute_failure_reason_counts(results),
        results=results,
    )


def evaluate_agent_response(
    case: EvaluationCase,
    response: AgentProcessResponse,
    latency_ms: float,
) -> EvaluationCaseResult:
    actual_tools = extract_actual_tools(response)
    policy_hit = has_policy_hit(
        expected_policy_keywords=case.expected_policy_keywords,
        policy_sources=response.policy_sources,
    )

    failure_reasons: list[str] = []
    if response.intent != case.expected_intent:
        failure_reasons.append(
            f"intent mismatch: expected {case.expected_intent}, got {response.intent}"
        )

    expected_tools = sorted(set(case.expected_tools))
    actual_tool_set = sorted(set(actual_tools))
    if actual_tool_set != expected_tools:
        failure_reasons.append(
            f"tools mismatch: expected {expected_tools}, got {actual_tool_set}"
        )

    if response.need_human != case.expected_need_human:
        failure_reasons.append(
            "need_human mismatch: expected "
            f"{case.expected_need_human}, got {response.need_human}"
        )

    if not policy_hit:
        failure_reasons.append(
            "policy miss: expected one of "
            f"{case.expected_policy_keywords} in policy title/source_file"
        )

    return EvaluationCaseResult(
        id=case.id,
        user_message=case.user_message,
        expected_intent=case.expected_intent,
        actual_intent=response.intent,
        expected_tools=case.expected_tools,
        actual_tools=actual_tools,
        expected_need_human=case.expected_need_human,
        actual_need_human=response.need_human,
        expected_policy_keywords=case.expected_policy_keywords,
        actual_policy_sources=response.policy_sources,
        latency_ms=round(latency_ms, 2),
        reply=response.reply,
        actions=response.actions,
        passed=not failure_reasons,
        failure_reasons=failure_reasons,
        policy_hit=policy_hit,
    )


def extract_actual_tools(response: AgentProcessResponse) -> list[str]:
    seen: set[str] = set()
    tools: list[str] = []
    for action in response.actions:
        if action.tool_name is None or action.tool_name in seen:
            continue
        seen.add(action.tool_name)
        tools.append(action.tool_name)
    return tools


def has_policy_hit(
    expected_policy_keywords: Sequence[str],
    policy_sources: Sequence[object],
) -> bool:
    haystack = " ".join(
        f"{getattr(source, 'policy_title', '')} {getattr(source, 'source_file', '')}"
        for source in policy_sources
    )
    return any(keyword in haystack for keyword in expected_policy_keywords)


def compute_metrics(results: Sequence[EvaluationCaseResult]) -> EvaluationMetrics:
    total = len(results)
    if total == 0:
        return EvaluationMetrics(
            intent_accuracy=0.0,
            tool_call_accuracy=0.0,
            policy_hit_rate=0.0,
            human_escalation_accuracy=0.0,
            average_latency_ms=0.0,
            auto_resolution_rate=0.0,
        )

    return EvaluationMetrics(
        intent_accuracy=_ratio(
            result.actual_intent == result.expected_intent for result in results
        ),
        tool_call_accuracy=_ratio(
            set(result.actual_tools) == set(result.expected_tools) for result in results
        ),
        policy_hit_rate=_ratio(result.policy_hit for result in results),
        human_escalation_accuracy=_ratio(
            result.actual_need_human == result.expected_need_human
            for result in results
        ),
        average_latency_ms=round(
            sum(result.latency_ms for result in results) / total,
            2,
        ),
        auto_resolution_rate=_ratio(not result.actual_need_human for result in results),
    )


def compute_metrics_by_intent(
    results: Sequence[EvaluationCaseResult],
) -> dict[AgentIntent, EvaluationIntentMetrics]:
    grouped: dict[AgentIntent, list[EvaluationCaseResult]] = {}
    for result in results:
        grouped.setdefault(result.expected_intent, []).append(result)

    return {
        intent: EvaluationIntentMetrics(
            total_cases=len(intent_results),
            passed_cases=sum(1 for result in intent_results if result.passed),
            failed_cases=sum(1 for result in intent_results if not result.passed),
            metrics=compute_metrics(intent_results),
        )
        for intent, intent_results in grouped.items()
    }


def compute_latency_percentiles(
    results: Sequence[EvaluationCaseResult],
) -> EvaluationLatencyPercentiles:
    latencies = sorted(result.latency_ms for result in results)
    if not latencies:
        return EvaluationLatencyPercentiles()

    return EvaluationLatencyPercentiles(
        p50_ms=_nearest_rank_percentile(latencies, 50),
        p95_ms=_nearest_rank_percentile(latencies, 95),
        max_ms=round(latencies[-1], 2),
    )


def compute_failure_reason_counts(
    results: Sequence[EvaluationCaseResult],
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for result in results:
        for reason in result.failure_reasons:
            counts[_failure_reason_category(reason)] += 1
    return dict(counts)


def write_evaluation_reports(
    report: EvaluationReport,
    json_path: Path | None = None,
    markdown_path: Path | None = None,
    history_dir: Path | None = None,
    write_history: bool = False,
) -> None:
    output_json_path = json_path or DEFAULT_EVAL_REPORT_PATH
    output_markdown_path = markdown_path or DEFAULT_EVAL_MARKDOWN_PATH
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_markdown_path.parent.mkdir(parents=True, exist_ok=True)

    output_json_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    output_markdown_path.write_text(
        render_markdown_report(report),
        encoding="utf-8",
    )

    if write_history:
        output_history_dir = history_dir or DEFAULT_EVAL_HISTORY_DIR
        output_history_dir.mkdir(parents=True, exist_ok=True)
        history_path = output_history_dir / _history_report_filename(report.generated_at)
        history_path.write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )


def read_latest_eval_report(path: Path | None = None) -> LatestEvaluationResponse:
    report_path = path or DEFAULT_EVAL_REPORT_PATH
    if not report_path.exists():
        raise FileNotFoundError(f"Evaluation report not found: {report_path}")

    report = _read_eval_report(report_path)
    failed_cases = [result for result in report.results if not result.passed]
    return LatestEvaluationResponse(
        mode=report.mode,
        llm_available=report.llm_available,
        llm_fallback=report.llm_fallback,
        generated_at=report.generated_at,
        total_cases=report.total_cases,
        passed_cases=report.passed_cases,
        failed_cases_count=report.failed_cases,
        metrics=report.metrics,
        metrics_by_intent=report.metrics_by_intent,
        latency_percentiles=report.latency_percentiles,
        failure_reason_counts=report.failure_reason_counts,
        failed_cases=failed_cases,
        tool_call_match_strategy=report.tool_call_match_strategy,
        policy_hit_strategy=report.policy_hit_strategy,
        database_write_strategy=report.database_write_strategy,
    )


def read_eval_history(
    history_dir: Path | None = None,
    limit: int = 20,
) -> EvaluationHistoryResponse:
    reports_dir = history_dir or DEFAULT_EVAL_HISTORY_DIR
    if not reports_dir.exists():
        return EvaluationHistoryResponse(total=0, reports=[])

    items: list[EvaluationHistoryItem] = []
    for path in reports_dir.glob("eval_report_*.json"):
        report = _read_eval_report(path)
        items.append(
            EvaluationHistoryItem(
                mode=report.mode,
                report_file=path.name,
                generated_at=report.generated_at,
                total_cases=report.total_cases,
                passed_cases=report.passed_cases,
                failed_cases=report.failed_cases,
                metrics=report.metrics,
                metrics_by_intent=report.metrics_by_intent,
                latency_percentiles=report.latency_percentiles,
                failure_reason_counts=report.failure_reason_counts,
            )
        )

    items.sort(key=lambda item: item.generated_at, reverse=True)
    bounded_limit = max(1, min(limit, 100))
    return EvaluationHistoryResponse(total=len(items), reports=items[:bounded_limit])


def read_eval_comparison(
    rules_path: Path | None = None,
    llm_path: Path | None = None,
) -> EvaluationCompareResponse:
    rules_report = _read_optional_mode_report("rules", rules_path)
    llm_report = _read_optional_mode_report("llm_assisted", llm_path)
    return EvaluationCompareResponse(
        rules_report=_to_report_summary(rules_report),
        llm_assisted_report=_to_report_summary(llm_report),
        diff_summary=_build_diff_summary(rules_report, llm_report),
        llm_status=_build_llm_status(llm_report),
    )


def render_markdown_report(report: EvaluationReport) -> str:
    metrics = report.metrics
    lines = [
        "# 客服 Agent 评测报告",
        "",
        f"- 生成时间：{report.generated_at.isoformat()}",
        f"- 评测集总数：{report.total_cases}",
        f"- 通过数：{report.passed_cases}",
        f"- 失败数：{report.failed_cases}",
        f"- 工具调用匹配方式：{report.tool_call_match_strategy}",
        f"- 政策命中方式：{report.policy_hit_strategy}",
        f"- 数据库写入策略：{report.database_write_strategy}",
        "",
        "## 指标",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| intent_accuracy | {_format_rate(metrics.intent_accuracy)} |",
        f"| tool_call_accuracy | {_format_rate(metrics.tool_call_accuracy)} |",
        f"| policy_hit_rate | {_format_rate(metrics.policy_hit_rate)} |",
        f"| human_escalation_accuracy | {_format_rate(metrics.human_escalation_accuracy)} |",
        f"| average_latency_ms | {metrics.average_latency_ms:.2f} |",
        f"| auto_resolution_rate | {_format_rate(metrics.auto_resolution_rate)} |",
        "",
        "## 延迟分位",
        "",
        "| 指标 | ms |",
        "| --- | ---: |",
        f"| p50 | {report.latency_percentiles.p50_ms:.2f} |",
        f"| p95 | {report.latency_percentiles.p95_ms:.2f} |",
        f"| max | {report.latency_percentiles.max_ms:.2f} |",
        "",
        "## 按 Intent 分组",
        "",
        (
            "| intent | total | passed | failed | intent_accuracy | "
            "policy_hit_rate | average_latency_ms |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for intent, intent_metrics in report.metrics_by_intent.items():
        lines.append(
            "| "
            f"{intent} | "
            f"{intent_metrics.total_cases} | "
            f"{intent_metrics.passed_cases} | "
            f"{intent_metrics.failed_cases} | "
            f"{_format_rate(intent_metrics.metrics.intent_accuracy)} | "
            f"{_format_rate(intent_metrics.metrics.policy_hit_rate)} | "
            f"{intent_metrics.metrics.average_latency_ms:.2f} |"
        )

    lines.extend(
        [
            "",
            "## 失败原因分类",
            "",
        ]
    )
    if report.failure_reason_counts:
        lines.extend(["| reason | count |", "| --- | ---: |"])
        for reason, count in report.failure_reason_counts.items():
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("无失败原因。")

    lines.extend(
        [
            "",
        "## 失败案例",
        "",
        ]
    )

    failed_results = [result for result in report.results if not result.passed]
    if not failed_results:
        lines.append("无失败案例。")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| id | expected_intent | actual_intent | expected_tools | actual_tools | failure_reasons |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for result in failed_results:
        lines.append(
            "| "
            f"{result.id} | "
            f"{result.expected_intent} | "
            f"{result.actual_intent} | "
            f"{', '.join(result.expected_tools)} | "
            f"{', '.join(result.actual_tools)} | "
            f"{'; '.join(result.failure_reasons)} |"
        )

    return "\n".join(lines) + "\n"


def _ratio(values: Sequence[bool] | object) -> float:
    materialized = list(values)  # type: ignore[arg-type]
    if not materialized:
        return 0.0
    return round(sum(1 for value in materialized if value) / len(materialized), 4)


def _format_rate(value: float) -> str:
    return f"{value * 100:.2f}%"


def _nearest_rank_percentile(values: Sequence[float], percentile: int) -> float:
    if not values:
        return 0.0
    rank = math.ceil((percentile / 100) * len(values))
    index = min(max(rank - 1, 0), len(values) - 1)
    return round(values[index], 2)


def _failure_reason_category(reason: str) -> str:
    if reason.startswith("intent mismatch"):
        return "intent_mismatch"
    if reason.startswith("tools mismatch"):
        return "tool_mismatch"
    if reason.startswith("need_human mismatch"):
        return "human_escalation_mismatch"
    if reason.startswith("policy miss"):
        return "policy_miss"
    return "other"


def _history_report_filename(generated_at: datetime) -> str:
    timestamp = generated_at.astimezone(UTC).strftime("%Y%m%d_%H%M%S")
    return f"eval_report_{timestamp}.json"


def _read_eval_report(path: Path) -> EvaluationReport:
    return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))


def _read_optional_mode_report(
    mode: AgentMode,
    explicit_path: Path | None,
) -> EvaluationReport | None:
    if explicit_path is not None:
        if not explicit_path.exists():
            return None
        report = _read_eval_report(explicit_path)
        if report.mode is None:
            report.mode = mode
        return report

    for candidate in _candidate_report_paths(mode):
        if candidate.exists():
            report = _read_eval_report(candidate)
            if report.mode is None:
                report.mode = mode
            return report

    return _read_latest_history_report_for_mode(mode)


def _candidate_report_paths(mode: AgentMode) -> list[Path]:
    if mode == "rules":
        return [DEFAULT_EVAL_REPORT_RULES_PATH, DEFAULT_EVAL_REPORT_PATH]
    return [DEFAULT_EVAL_REPORT_LLM_ASSISTED_PATH]


def _read_latest_history_report_for_mode(mode: AgentMode) -> EvaluationReport | None:
    if not DEFAULT_EVAL_HISTORY_DIR.exists():
        return None

    reports: list[EvaluationReport] = []
    for path in DEFAULT_EVAL_HISTORY_DIR.glob("eval_report_*.json"):
        report = _read_eval_report(path)
        if report.mode == mode or (mode == "rules" and report.mode is None):
            if report.mode is None:
                report.mode = mode
            reports.append(report)

    if not reports:
        return None
    return max(reports, key=lambda report: report.generated_at)


def _to_report_summary(report: EvaluationReport | None) -> EvaluationReportSummary | None:
    if report is None:
        return None
    return EvaluationReportSummary(
        mode=report.mode,
        llm_available=report.llm_available,
        llm_fallback=report.llm_fallback,
        generated_at=report.generated_at,
        total_cases=report.total_cases,
        passed_cases=report.passed_cases,
        failed_cases_count=report.failed_cases,
        metrics=report.metrics,
        metrics_by_intent=report.metrics_by_intent,
        latency_percentiles=report.latency_percentiles,
        failure_reason_counts=report.failure_reason_counts,
    )


def _build_diff_summary(
    rules_report: EvaluationReport | None,
    llm_report: EvaluationReport | None,
) -> EvaluationDiffSummary:
    if rules_report is None or llm_report is None:
        return EvaluationDiffSummary()

    rules_by_id = {result.id: result for result in rules_report.results}
    llm_by_id = {result.id: result for result in llm_report.results}
    shared_ids = sorted(rules_by_id.keys() & llm_by_id.keys())

    rules_failed_llm_passed: list[EvaluationComparisonCase] = []
    llm_failed_rules_passed: list[EvaluationComparisonCase] = []
    both_failed: list[EvaluationComparisonCase] = []
    for case_id in shared_ids:
        rules_result = rules_by_id[case_id]
        llm_result = llm_by_id[case_id]
        comparison_case = _to_comparison_case(rules_result, llm_result)
        if not rules_result.passed and llm_result.passed:
            rules_failed_llm_passed.append(comparison_case)
        elif rules_result.passed and not llm_result.passed:
            llm_failed_rules_passed.append(comparison_case)
        elif not rules_result.passed and not llm_result.passed:
            both_failed.append(comparison_case)

    return EvaluationDiffSummary(
        metric_deltas=_metric_deltas(rules_report, llm_report),
        intent_deltas=_intent_deltas(rules_report, llm_report),
        rules_failed_llm_passed=rules_failed_llm_passed,
        llm_failed_rules_passed=llm_failed_rules_passed,
        both_failed=both_failed,
    )


def _metric_deltas(
    rules_report: EvaluationReport,
    llm_report: EvaluationReport,
) -> dict[str, float]:
    rules_values = _report_metric_values(rules_report)
    llm_values = _report_metric_values(llm_report)
    return {
        metric: round(llm_values[metric] - rules_values[metric], 4)
        for metric in COMPARISON_METRIC_NAMES
    }


def _intent_deltas(
    rules_report: EvaluationReport,
    llm_report: EvaluationReport,
) -> dict[AgentIntent, dict[str, float]]:
    intents = sorted(
        set(rules_report.metrics_by_intent) | set(llm_report.metrics_by_intent)
    )
    deltas: dict[AgentIntent, dict[str, float]] = {}
    for intent in intents:
        rules_values = _intent_metric_values(rules_report.metrics_by_intent.get(intent))
        llm_values = _intent_metric_values(llm_report.metrics_by_intent.get(intent))
        deltas[intent] = {
            metric: round(llm_values[metric] - rules_values[metric], 4)
            for metric in COMPARISON_METRIC_NAMES
        }
    return deltas


def _report_metric_values(report: EvaluationReport) -> dict[str, float]:
    return {
        "intent_accuracy": report.metrics.intent_accuracy,
        "tool_call_accuracy": report.metrics.tool_call_accuracy,
        "policy_hit_rate": report.metrics.policy_hit_rate,
        "human_escalation_accuracy": report.metrics.human_escalation_accuracy,
        "auto_resolution_rate": report.metrics.auto_resolution_rate,
        "average_latency_ms": report.metrics.average_latency_ms,
        "p50_ms": report.latency_percentiles.p50_ms,
        "p95_ms": report.latency_percentiles.p95_ms,
        "max_ms": report.latency_percentiles.max_ms,
        "total_cases": float(report.total_cases),
        "passed_cases": float(report.passed_cases),
        "failed_cases_count": float(report.failed_cases),
    }


def _intent_metric_values(
    item: EvaluationIntentMetrics | None,
) -> dict[str, float]:
    if item is None:
        return {metric: 0.0 for metric in COMPARISON_METRIC_NAMES}
    return {
        "intent_accuracy": item.metrics.intent_accuracy,
        "tool_call_accuracy": item.metrics.tool_call_accuracy,
        "policy_hit_rate": item.metrics.policy_hit_rate,
        "human_escalation_accuracy": item.metrics.human_escalation_accuracy,
        "auto_resolution_rate": item.metrics.auto_resolution_rate,
        "average_latency_ms": item.metrics.average_latency_ms,
        "p50_ms": 0.0,
        "p95_ms": 0.0,
        "max_ms": 0.0,
        "total_cases": float(item.total_cases),
        "passed_cases": float(item.passed_cases),
        "failed_cases_count": float(item.failed_cases),
    }


def _to_comparison_case(
    rules_result: EvaluationCaseResult,
    llm_result: EvaluationCaseResult,
) -> EvaluationComparisonCase:
    return EvaluationComparisonCase(
        id=rules_result.id,
        user_message=rules_result.user_message,
        expected_intent=rules_result.expected_intent,
        rules_passed=rules_result.passed,
        llm_assisted_passed=llm_result.passed,
        rules_actual_intent=rules_result.actual_intent,
        llm_assisted_actual_intent=llm_result.actual_intent,
        rules_failure_reasons=rules_result.failure_reasons,
        llm_assisted_failure_reasons=llm_result.failure_reasons,
        rules_latency_ms=rules_result.latency_ms,
        llm_assisted_latency_ms=llm_result.latency_ms,
    )


def _build_llm_status(llm_report: EvaluationReport | None) -> EvaluationLlmStatus:
    configured = _is_llm_configured()
    fallback_likely = (
        not configured
        or bool(llm_report and llm_report.llm_fallback)
        or bool(llm_report and llm_report.llm_available is False)
    )
    if fallback_likely:
        message = "当前增强模式未连接模型或已回退，结果可能与规则模式一致。"
    elif llm_report is None:
        message = "尚未生成增强模式评测报告。"
    else:
        message = "增强模式报告已生成，可对比规则模式的处理质量和耗时。"
    return EvaluationLlmStatus(
        configured=configured,
        fallback_likely=fallback_likely,
        message=message,
    )


def _is_llm_configured() -> bool:
    return bool(os.getenv("DASHSCOPE_API_KEY", "").strip())
