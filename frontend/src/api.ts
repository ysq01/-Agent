import type {
  AdminPolicyActionResponse,
  AdminPolicyCreateRequest,
  AdminPolicyListResponse,
  AdminPolicyStatus,
  AdminPolicyUpdateRequest,
  AdminSessionResponse,
  AdminEvaluationCompareResponse,
  AdminEvaluationJobStatusResponse,
  AgentFeedbackCreateRequest,
  AgentFeedbackCreateResponse,
  AgentProcessRequest,
  AgentProcessResponse,
  EvaluationHistoryResponse,
  FeedbackSummaryResponse,
  KnowledgeDocumentListResponse,
  LatestEvaluationResponse,
  PolicySearchResponse,
  TicketDetail,
  TicketFilters,
  TicketListResponse,
  TicketStatusUpdateRequest,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

type ApiErrorPayload = {
  detail?: string | { code?: string; message?: string };
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as ApiErrorPayload;
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail?.message) {
        message = payload.detail.message;
      }
    } catch {
      message = response.statusText || message;
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const value = search.toString();
  return value ? `?${value}` : "";
}

function bearerHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
  };
}

export function processAgent(
  request: AgentProcessRequest,
): Promise<AgentProcessResponse> {
  return fetchJson<AgentProcessResponse>("/api/agent/process", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function createAgentFeedback(
  request: AgentFeedbackCreateRequest,
): Promise<AgentFeedbackCreateResponse> {
  return fetchJson<AgentFeedbackCreateResponse>("/api/agent/feedback", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function listTickets(filters: TicketFilters): Promise<TicketListResponse> {
  return fetchJson<TicketListResponse>(
    `/api/tickets${buildQuery({
      status: filters.status,
      category: filters.category,
      priority: filters.priority,
      page: filters.page ?? 1,
      page_size: filters.page_size ?? 10,
    })}`,
  );
}

export function getTicket(ticketNumber: string): Promise<TicketDetail> {
  return fetchJson<TicketDetail>(`/api/tickets/${encodeURIComponent(ticketNumber)}`);
}

export function updateTicketStatus(
  ticketNumber: string,
  request: TicketStatusUpdateRequest,
): Promise<TicketDetail> {
  return fetchJson<TicketDetail>(
    `/api/tickets/${encodeURIComponent(ticketNumber)}/status`,
    {
      method: "PATCH",
      body: JSON.stringify(request),
    },
  );
}

export function listKnowledgeDocuments(): Promise<KnowledgeDocumentListResponse> {
  return fetchJson<KnowledgeDocumentListResponse>("/api/knowledge/documents");
}

export function searchPolicies(
  query: string,
  topK = 3,
): Promise<PolicySearchResponse> {
  return fetchJson<PolicySearchResponse>("/api/tools/policies/search", {
    method: "POST",
    body: JSON.stringify({ query, top_k: topK }),
  });
}

export function getLatestEvaluation(): Promise<LatestEvaluationResponse> {
  return fetchJson<LatestEvaluationResponse>("/api/eval/latest");
}

export function getEvaluationHistory(limit = 12): Promise<EvaluationHistoryResponse> {
  return fetchJson<EvaluationHistoryResponse>(
    `/api/eval/history${buildQuery({ limit })}`,
  );
}

export function getFeedbackSummary(): Promise<FeedbackSummaryResponse> {
  return fetchJson<FeedbackSummaryResponse>("/api/eval/feedback-summary");
}

export function adminLogin(
  username: string,
  password: string,
): Promise<AdminSessionResponse> {
  return fetchJson<AdminSessionResponse>("/api/admin/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function adminLogout(token: string): Promise<{ success: boolean }> {
  return fetchJson<{ success: boolean }>("/api/admin/logout", {
    method: "POST",
    headers: bearerHeaders(token),
  });
}

export function listAdminPolicies(
  token: string,
  status?: AdminPolicyStatus | "",
): Promise<AdminPolicyListResponse> {
  return fetchJson<AdminPolicyListResponse>(
    `/api/admin/policies${buildQuery({ status })}`,
    {
      headers: bearerHeaders(token),
    },
  );
}

export function createAdminPolicy(
  token: string,
  request: AdminPolicyCreateRequest,
): Promise<AdminPolicyActionResponse["policy"]> {
  return fetchJson<AdminPolicyActionResponse["policy"]>("/api/admin/policies", {
    method: "POST",
    headers: bearerHeaders(token),
    body: JSON.stringify(request),
  });
}

export function updateAdminPolicy(
  token: string,
  policyId: number,
  request: AdminPolicyUpdateRequest,
): Promise<AdminPolicyActionResponse["policy"]> {
  return fetchJson<AdminPolicyActionResponse["policy"]>(
    `/api/admin/policies/${encodeURIComponent(policyId)}`,
    {
      method: "PATCH",
      headers: bearerHeaders(token),
      body: JSON.stringify(request),
    },
  );
}

export function publishAdminPolicy(
  token: string,
  policyId: number,
): Promise<AdminPolicyActionResponse> {
  return fetchJson<AdminPolicyActionResponse>(
    `/api/admin/policies/${encodeURIComponent(policyId)}/publish`,
    {
      method: "POST",
      headers: bearerHeaders(token),
    },
  );
}

export function disableAdminPolicy(
  token: string,
  policyId: number,
): Promise<AdminPolicyActionResponse> {
  return fetchJson<AdminPolicyActionResponse>(
    `/api/admin/policies/${encodeURIComponent(policyId)}/disable`,
    {
      method: "POST",
      headers: bearerHeaders(token),
    },
  );
}

export function getAdminEvaluationCompare(
  token: string,
): Promise<AdminEvaluationCompareResponse> {
  return fetchJson<AdminEvaluationCompareResponse>("/api/admin/eval/compare", {
    headers: bearerHeaders(token),
  });
}

export function runAdminLlmAssistedEvaluation(
  token: string,
): Promise<AdminEvaluationJobStatusResponse> {
  return fetchJson<AdminEvaluationJobStatusResponse>(
    "/api/admin/eval/llm-assisted/run",
    {
      method: "POST",
      headers: bearerHeaders(token),
    },
  );
}

export function getAdminLlmAssistedEvaluationStatus(
  token: string,
): Promise<AdminEvaluationJobStatusResponse> {
  return fetchJson<AdminEvaluationJobStatusResponse>(
    "/api/admin/eval/llm-assisted/status",
    {
      headers: bearerHeaders(token),
    },
  );
}
