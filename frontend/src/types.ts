export type AgentActionStatus = "success" | "skipped" | "failed";

export type AgentMode = "rules" | "llm_assisted";

export type AgentFeedbackType = "accepted" | "edited" | "rejected";

export type AdminRole = "admin" | "operator";

export type AdminPolicyStatus = "draft" | "published" | "disabled";

export type AgentAction = {
  node: string;
  tool_name: string | null;
  status: AgentActionStatus;
  summary: string;
  metadata: Record<string, unknown>;
};

export type AgentPolicySource = {
  policy_title: string;
  source_file: string;
  score: number;
};

export type AgentProcessRequest = {
  message: string;
  order_number?: string;
  external_id?: string;
  ticket_number?: string;
  requested_amount?: string;
  mode?: AgentMode;
};

export type AgentProcessResponse = {
  intent: string;
  reply: string;
  actions: AgentAction[];
  policy_sources: AgentPolicySource[];
  need_human: boolean;
  ticket_id: string | null;
  confidence: number;
};

export type AgentFeedbackCreateRequest = {
  message: string;
  intent: string;
  ai_reply: string;
  final_reply?: string;
  feedback_type: AgentFeedbackType;
  reason?: string;
  ticket_number?: string;
  order_number?: string;
  agent_mode?: AgentMode;
};

export type AgentFeedbackCreateResponse = {
  id: number;
  feedback_type: AgentFeedbackType;
  created_at: string;
};

export type FeedbackRecentItem = {
  id: number;
  feedback_type: AgentFeedbackType;
  reason: string | null;
  message_preview: string;
  final_reply_preview: string | null;
  created_at: string;
};

export type FeedbackSummaryResponse = {
  total: number;
  accepted_count: number;
  edited_count: number;
  rejected_count: number;
  accepted_rate: number;
  edited_rate: number;
  rejected_rate: number;
  reason_counts: Record<string, number>;
  recent_feedback: FeedbackRecentItem[];
};

export type AdminSessionResponse = {
  token: string;
  role: AdminRole;
  expires_at: string;
};

export type AdminPolicy = {
  id: number;
  title: string;
  content: string;
  status: AdminPolicyStatus;
  version: number;
  source: string;
  supersedes_policy_id: number | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  disabled_at: string | null;
};

export type AdminPolicyListResponse = {
  total: number;
  policies: AdminPolicy[];
};

export type AdminPolicyCreateRequest = {
  title: string;
  content: string;
};

export type AdminPolicyUpdateRequest = {
  title?: string;
  content?: string;
};

export type AdminPolicyActionResponse = {
  policy: AdminPolicy;
  knowledge_updated: boolean;
};

export type TicketListItem = {
  ticket_number: string;
  order_number: string;
  external_id: string;
  category: string;
  status: string;
  priority: string;
  handled_by_ai: boolean;
  is_escalated: boolean;
  created_at: string | null;
};

export type TicketListResponse = {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  tickets: TicketListItem[];
};

export type TicketDetail = TicketListItem & {
  subject: string;
  description: string;
  resolution: string | null;
  updated_at: string | null;
  order_summary: {
    order_number: string;
    status: string;
    payment_status: string;
    total_amount: string;
    placed_at: string;
  };
  user_summary: {
    external_id: string;
    name: string;
    tier: string;
  };
};

export type TicketStatusUpdateRequest = {
  status: string;
  resolution?: string;
};

export type TicketFilters = {
  status?: string;
  category?: string;
  priority?: string;
  page?: number;
  page_size?: number;
};

export type KnowledgeDocument = {
  policy_title: string;
  source_file: string;
  character_count: number;
  preview: string;
  content: string;
};

export type KnowledgeDocumentListResponse = {
  total: number;
  documents: KnowledgeDocument[];
};

export type PolicySearchResult = {
  policy_title: string;
  matched_text: string;
  score: number;
  source_file: string;
};

export type PolicySearchResponse = {
  tool_name: "search_policy";
  query: string;
  results: PolicySearchResult[];
};

export type EvaluationMetrics = {
  intent_accuracy: number;
  tool_call_accuracy: number;
  policy_hit_rate: number;
  human_escalation_accuracy: number;
  average_latency_ms: number;
  auto_resolution_rate: number;
};

export type EvaluationIntentMetrics = {
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  metrics: EvaluationMetrics;
};

export type EvaluationLatencyPercentiles = {
  p50_ms: number;
  p95_ms: number;
  max_ms: number;
};

export type EvaluationCaseResult = {
  id: string;
  user_message: string;
  expected_intent: string;
  actual_intent: string;
  expected_tools: string[];
  actual_tools: string[];
  expected_need_human: boolean;
  actual_need_human: boolean;
  expected_policy_keywords: string[];
  actual_policy_sources: AgentPolicySource[];
  latency_ms: number;
  reply: string;
  actions: AgentAction[];
  passed: boolean;
  failure_reasons: string[];
  policy_hit: boolean;
};

export type LatestEvaluationResponse = {
  generated_at: string;
  total_cases: number;
  passed_cases: number;
  failed_cases_count: number;
  metrics: EvaluationMetrics;
  metrics_by_intent: Record<string, EvaluationIntentMetrics>;
  latency_percentiles: EvaluationLatencyPercentiles;
  failure_reason_counts: Record<string, number>;
  failed_cases: EvaluationCaseResult[];
  tool_call_match_strategy: string;
  policy_hit_strategy: string;
  database_write_strategy: string;
};

export type EvaluationHistoryItem = {
  report_file: string;
  generated_at: string;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  metrics: EvaluationMetrics;
  metrics_by_intent: Record<string, EvaluationIntentMetrics>;
  latency_percentiles: EvaluationLatencyPercentiles;
  failure_reason_counts: Record<string, number>;
};

export type EvaluationHistoryResponse = {
  total: number;
  reports: EvaluationHistoryItem[];
};

export type AdminEvaluationReportSummary = {
  mode: AgentMode | null;
  llm_available: boolean | null;
  llm_fallback: boolean | null;
  generated_at: string;
  total_cases: number;
  passed_cases: number;
  failed_cases_count: number;
  metrics: EvaluationMetrics;
  metrics_by_intent: Record<string, EvaluationIntentMetrics>;
  latency_percentiles: EvaluationLatencyPercentiles;
  failure_reason_counts: Record<string, number>;
};

export type EvaluationComparisonCase = {
  id: string;
  user_message: string;
  expected_intent: string;
  rules_passed: boolean;
  llm_assisted_passed: boolean;
  rules_actual_intent: string;
  llm_assisted_actual_intent: string;
  rules_failure_reasons: string[];
  llm_assisted_failure_reasons: string[];
  rules_latency_ms: number;
  llm_assisted_latency_ms: number;
};

export type EvaluationDiffSummary = {
  metric_deltas: Record<string, number>;
  intent_deltas: Record<string, Record<string, number>>;
  rules_failed_llm_passed: EvaluationComparisonCase[];
  llm_failed_rules_passed: EvaluationComparisonCase[];
  both_failed: EvaluationComparisonCase[];
};

export type EvaluationLlmStatus = {
  configured: boolean;
  fallback_likely: boolean;
  message: string;
};

export type AdminEvaluationJobStatusValue =
  | "idle"
  | "running"
  | "succeeded"
  | "failed";

export type AdminEvaluationJobStatusResponse = {
  status: AdminEvaluationJobStatusValue;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  report_generated_at: string | null;
};

export type AdminEvaluationCompareResponse = {
  rules_report: AdminEvaluationReportSummary | null;
  llm_assisted_report: AdminEvaluationReportSummary | null;
  diff_summary: EvaluationDiffSummary;
  llm_status: EvaluationLlmStatus;
};
