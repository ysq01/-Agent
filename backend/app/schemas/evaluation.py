from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agent import AgentAction, AgentIntent, AgentMode, AgentPolicySource


EvaluationToolName = Literal[
    "search_policy",
    "get_order_info",
    "check_refund_eligibility",
    "create_ticket",
    "escalate_to_human",
]


class EvaluationSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class EvaluationCase(EvaluationSchema):
    id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    expected_intent: AgentIntent
    expected_tools: list[EvaluationToolName]
    expected_need_human: bool
    expected_policy_keywords: list[str] = Field(min_length=1)


class EvaluationCaseResult(EvaluationSchema):
    id: str
    user_message: str
    expected_intent: AgentIntent
    actual_intent: AgentIntent
    expected_tools: list[EvaluationToolName]
    actual_tools: list[str]
    expected_need_human: bool
    actual_need_human: bool
    expected_policy_keywords: list[str]
    actual_policy_sources: list[AgentPolicySource]
    latency_ms: float
    reply: str
    actions: list[AgentAction]
    passed: bool
    failure_reasons: list[str]
    policy_hit: bool


class EvaluationMetrics(EvaluationSchema):
    intent_accuracy: float
    tool_call_accuracy: float
    policy_hit_rate: float
    human_escalation_accuracy: float
    average_latency_ms: float
    auto_resolution_rate: float


class EvaluationIntentMetrics(EvaluationSchema):
    total_cases: int
    passed_cases: int
    failed_cases: int
    metrics: EvaluationMetrics


class EvaluationLatencyPercentiles(EvaluationSchema):
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    max_ms: float = 0.0


class EvaluationReport(EvaluationSchema):
    mode: AgentMode | None = None
    llm_available: bool | None = None
    llm_fallback: bool | None = None
    generated_at: datetime
    total_cases: int
    passed_cases: int
    failed_cases: int
    metrics: EvaluationMetrics
    metrics_by_intent: dict[AgentIntent, EvaluationIntentMetrics] = Field(default_factory=dict)
    latency_percentiles: EvaluationLatencyPercentiles = Field(
        default_factory=EvaluationLatencyPercentiles
    )
    failure_reason_counts: dict[str, int] = Field(default_factory=dict)
    results: list[EvaluationCaseResult]
    tool_call_match_strategy: str = (
        "Deduplicated set exact match over Agent actions.tool_name; None values are ignored."
    )
    policy_hit_strategy: str = (
        "A case is a policy hit when any expected_policy_keywords value appears in "
        "policy_sources.policy_title or policy_sources.source_file."
    )
    database_write_strategy: str = (
        "The default script runs Agent calls inside an outer database transaction and "
        "rolls it back after writing reports, so eval-created or escalated tickets do "
        "not persist unless persist mode is explicitly used."
    )


class LatestEvaluationResponse(EvaluationSchema):
    mode: AgentMode | None = None
    llm_available: bool | None = None
    llm_fallback: bool | None = None
    generated_at: datetime
    total_cases: int
    passed_cases: int
    failed_cases_count: int
    metrics: EvaluationMetrics
    metrics_by_intent: dict[AgentIntent, EvaluationIntentMetrics]
    latency_percentiles: EvaluationLatencyPercentiles
    failure_reason_counts: dict[str, int]
    failed_cases: list[EvaluationCaseResult]
    tool_call_match_strategy: str
    policy_hit_strategy: str
    database_write_strategy: str


class EvaluationHistoryItem(EvaluationSchema):
    mode: AgentMode | None = None
    report_file: str
    generated_at: datetime
    total_cases: int
    passed_cases: int
    failed_cases: int
    metrics: EvaluationMetrics
    metrics_by_intent: dict[AgentIntent, EvaluationIntentMetrics]
    latency_percentiles: EvaluationLatencyPercentiles
    failure_reason_counts: dict[str, int]


class EvaluationHistoryResponse(EvaluationSchema):
    total: int
    reports: list[EvaluationHistoryItem]


class EvaluationReportSummary(EvaluationSchema):
    mode: AgentMode | None = None
    llm_available: bool | None = None
    llm_fallback: bool | None = None
    generated_at: datetime
    total_cases: int
    passed_cases: int
    failed_cases_count: int
    metrics: EvaluationMetrics
    metrics_by_intent: dict[AgentIntent, EvaluationIntentMetrics]
    latency_percentiles: EvaluationLatencyPercentiles
    failure_reason_counts: dict[str, int]


class EvaluationComparisonCase(EvaluationSchema):
    id: str
    user_message: str
    expected_intent: AgentIntent
    rules_passed: bool
    llm_assisted_passed: bool
    rules_actual_intent: AgentIntent
    llm_assisted_actual_intent: AgentIntent
    rules_failure_reasons: list[str]
    llm_assisted_failure_reasons: list[str]
    rules_latency_ms: float
    llm_assisted_latency_ms: float


class EvaluationDiffSummary(EvaluationSchema):
    metric_deltas: dict[str, float] = Field(default_factory=dict)
    intent_deltas: dict[AgentIntent, dict[str, float]] = Field(default_factory=dict)
    rules_failed_llm_passed: list[EvaluationComparisonCase] = Field(default_factory=list)
    llm_failed_rules_passed: list[EvaluationComparisonCase] = Field(default_factory=list)
    both_failed: list[EvaluationComparisonCase] = Field(default_factory=list)


class EvaluationLlmStatus(EvaluationSchema):
    configured: bool
    fallback_likely: bool
    message: str


EvaluationJobStatusValue = Literal["idle", "running", "succeeded", "failed"]


class LlmAssistedEvaluationJobStatus(EvaluationSchema):
    status: EvaluationJobStatusValue
    message: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    report_generated_at: datetime | None = None


class EvaluationCompareResponse(EvaluationSchema):
    rules_report: EvaluationReportSummary | None
    llm_assisted_report: EvaluationReportSummary | None
    diff_summary: EvaluationDiffSummary
    llm_status: EvaluationLlmStatus
