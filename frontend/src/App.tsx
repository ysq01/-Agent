import { FormEvent, type ReactNode, useEffect, useState } from "react";
import {
  adminLogin,
  adminLogout,
  createAdminPolicy,
  createAgentFeedback,
  disableAdminPolicy,
  getAdminEvaluationCompare,
  getAdminLlmAssistedEvaluationStatus,
  getEvaluationHistory,
  getFeedbackSummary,
  getLatestEvaluation,
  getTicket,
  listAdminPolicies,
  listKnowledgeDocuments,
  listTickets,
  publishAdminPolicy,
  processAgent,
  runAdminLlmAssistedEvaluation,
  searchPolicies,
  updateAdminPolicy,
  updateTicketStatus,
} from "./api";
import {
  describeIntent,
  intentSortValue,
  labelCategory,
  labelFeedbackType,
  labelFailureReason,
  labelIntent,
  labelMetric,
  labelOrderStatus,
  labelPaymentStatus,
  labelPolicyStatus,
  labelPriority,
  labelStatus,
  localizeServiceReply,
  policyStatusTone,
  policyScenario,
  priorityTone,
  statusTone,
} from "./presentation";
import type { BadgeTone } from "./presentation";
import type {
  AdminPolicy,
  AdminPolicyCreateRequest,
  AdminPolicyStatus,
  AdminPolicyUpdateRequest,
  AdminSessionResponse,
  AdminEvaluationCompareResponse,
  AdminEvaluationJobStatusResponse,
  AdminEvaluationReportSummary,
  AgentFeedbackCreateRequest,
  AgentFeedbackType,
  AgentMode,
  AgentProcessRequest,
  AgentProcessResponse,
  EvaluationCaseResult,
  EvaluationHistoryItem,
  FeedbackSummaryResponse,
  KnowledgeDocument,
  LatestEvaluationResponse,
  PolicySearchResult,
  TicketDetail,
  TicketFilters,
  TicketListItem,
  TicketStatusUpdateRequest,
} from "./types";

type PageKey = "chat" | "tickets" | "knowledge" | "evaluation" | "admin";
type AdminTabKey = "policies" | "compare";

type SelectOption = {
  value: string;
  label: string;
};

const comparisonMetricKeys = [
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
];

type AgentFeedbackContext = {
  message: string;
  order_number?: string;
  ticket_number?: string;
  agent_mode: AgentMode;
};

const LAST_AGENT_RUN_KEY = "kefu-agent-last-run";
const LAST_AGENT_CONTEXT_KEY = "kefu-agent-last-context";
const SMART_ASSIST_PREF_KEY = "kefu-agent-smart-assist-enabled";
const ADMIN_SESSION_KEY = "kefu-agent-admin-session";

const servicePages: Array<{ key: PageKey; label: string; description: string }> = [
  {
    key: "chat",
    label: "客服处理台",
    description: "输入用户问题，生成处理建议和回复草稿。",
  },
  {
    key: "tickets",
    label: "工单中心",
    description: "查看售后工单队列和处理状态。",
  },
  {
    key: "knowledge",
    label: "政策知识库",
    description: "浏览售后政策，并验证政策检索效果。",
  },
  {
    key: "evaluation",
    label: "质检中心",
    description: "查看自动处理质量和历史趋势。",
  },
];

const adminPages: Array<{ key: PageKey; label: string; description: string }> = [
  {
    key: "admin",
    label: "后台管理",
    description: "管理政策草稿、发布和停用。",
  },
];

const pages = [...servicePages, ...adminPages];

const examples = [
  {
    label: "退款审核",
    description: "破损商品，含申请金额",
    message: "ORD-2026-0002 商品坏了我要退款",
    requested_amount: "50.00",
  },
  {
    label: "物流异常",
    description: "订单物流长时间未更新",
    message: "订单 ORD-2026-0001 的物流一直没更新",
  },
  {
    label: "发票服务",
    description: "用户申请开具发票",
    message: "请帮我给 ORD-2026-0031 开一张发票",
  },
  {
    label: "投诉升级",
    description: "售后处理超时投诉",
    message: "我要投诉，ORD-2026-0031 的售后处理太慢了",
  },
];

const statusOptions: SelectOption[] = [
  { value: "open", label: "待处理" },
  { value: "pending", label: "处理中" },
  { value: "escalated", label: "已转人工" },
  { value: "resolved", label: "已解决" },
  { value: "closed", label: "已关闭" },
];

const categoryOptions: SelectOption[] = [
  { value: "refund", label: "退款售后" },
  { value: "delivery", label: "物流配送" },
  { value: "invoice", label: "发票服务" },
  { value: "product_quality", label: "商品质量" },
  { value: "exchange", label: "换货服务" },
];

const priorityOptions: SelectOption[] = [
  { value: "low", label: "低" },
  { value: "medium", label: "中" },
  { value: "high", label: "高" },
];

const feedbackOptions: Array<{ value: AgentFeedbackType; label: string }> = [
  { value: "accepted", label: "采纳" },
  { value: "edited", label: "修改后采纳" },
  { value: "rejected", label: "不采纳" },
];

const adminPolicyStatusOptions: Array<{ value: AdminPolicyStatus; label: string }> = [
  { value: "draft", label: "草稿" },
  { value: "published", label: "已发布" },
  { value: "disabled", label: "已停用" },
];

function App() {
  const [activePage, setActivePage] = useState<PageKey>("chat");
  const [lastAgentRun, setLastAgentRun] = useState<AgentProcessResponse | null>(() =>
    readLastAgentRun(),
  );
  const [lastAgentContext, setLastAgentContext] = useState<AgentFeedbackContext | null>(
    () => readLastAgentContext(),
  );

  const currentPage = pages.find((page) => page.key === activePage) ?? pages[0];

  function saveLastAgentRun(
    result: AgentProcessResponse,
    context: AgentFeedbackContext,
  ) {
    setLastAgentRun(result);
    setLastAgentContext(context);
    localStorage.setItem(LAST_AGENT_RUN_KEY, JSON.stringify(result));
    localStorage.setItem(LAST_AGENT_CONTEXT_KEY, JSON.stringify(context));
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">KA</div>
          <div>
            <strong>智能客服助手</strong>
            <span>售后自动化工作台</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="主导航">
          {servicePages.map((page) => (
            <button
              className={page.key === activePage ? "nav-item active" : "nav-item"}
              key={page.key}
              onClick={() => setActivePage(page.key)}
              type="button"
            >
              <span>{page.label}</span>
              <small>{page.description}</small>
            </button>
          ))}
          <div className="nav-divider">管理端</div>
          {adminPages.map((page) => (
            <button
              className={page.key === activePage ? "nav-item active" : "nav-item"}
              key={page.key}
              onClick={() => setActivePage(page.key)}
              type="button"
            >
              <span>{page.label}</span>
              <small>{page.description}</small>
            </button>
          ))}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">售后服务工作台</p>
            <h1>{currentPage.label}</h1>
            <p className="page-description">{currentPage.description}</p>
          </div>
          <div className="topbar-meta" aria-label="项目能力">
            <span>智能建议</span>
            <span>售后政策</span>
            <span>服务质检</span>
          </div>
        </header>

        {activePage === "chat" && (
          <ChatPage
            lastAgentContext={lastAgentContext}
            lastAgentRun={lastAgentRun}
            onResult={saveLastAgentRun}
          />
        )}
        {activePage === "tickets" && <TicketsPage />}
        {activePage === "knowledge" && <KnowledgePage />}
        {activePage === "evaluation" && <EvaluationPage />}
        {activePage === "admin" && <AdminPage />}
      </main>
    </div>
  );
}

function AdminPage() {
  const [session, setSession] = useState<AdminSessionResponse | null>(() =>
    readAdminSession(),
  );

  function handleLogin(nextSession: AdminSessionResponse) {
    setSession(nextSession);
    localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(nextSession));
  }

  async function handleLogout() {
    const currentToken = session?.token;
    setSession(null);
    localStorage.removeItem(ADMIN_SESSION_KEY);
    if (currentToken) {
      try {
        await adminLogout(currentToken);
      } catch {
        // Local logout should still clear the browser session.
      }
    }
  }

  if (!session) {
    return <AdminLoginPanel onLogin={handleLogin} />;
  }

  return <AdminWorkspace onLogout={handleLogout} session={session} />;
}

function AdminWorkspace({
  onLogout,
  session,
}: {
  onLogout: () => void;
  session: AdminSessionResponse;
}) {
  const [activeTab, setActiveTab] = useState<AdminTabKey>("policies");

  return (
    <section className="admin-workspace">
      <div className="panel admin-tabs-panel">
        <div>
          <h2>后台管理</h2>
          <p className="muted">管理员可维护政策，并查看规则模式与增强模式的质检差异。</p>
        </div>
        <div className="admin-tab-row" role="tablist" aria-label="后台管理功能">
          <button
            aria-selected={activeTab === "policies"}
            className={activeTab === "policies" ? "admin-tab active" : "admin-tab"}
            onClick={() => setActiveTab("policies")}
            role="tab"
            type="button"
          >
            政策管理
          </button>
          <button
            aria-selected={activeTab === "compare"}
            className={activeTab === "compare" ? "admin-tab active" : "admin-tab"}
            onClick={() => setActiveTab("compare")}
            role="tab"
            type="button"
          >
            模型效果对比
          </button>
          <button className="secondary-button" onClick={onLogout} type="button">
            退出后台
          </button>
        </div>
      </div>

      {activeTab === "policies" ? (
        <AdminPolicyManager session={session} />
      ) : (
        <AdminEvaluationComparePage session={session} />
      )}
    </section>
  );
}

function AdminLoginPanel({
  onLogin,
}: {
  onLogin: (session: AdminSessionResponse) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      onLogin(await adminLogin(username.trim(), password));
    } catch {
      setError("登录失败，请检查管理员账号和密码。");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="admin-login-layout">
      <form className="panel admin-login-panel" onSubmit={submit}>
        <div className="panel-heading">
          <div>
            <h2>后台登录</h2>
            <p>管理员登录后可维护售后政策草稿、发布和停用状态。</p>
          </div>
        </div>

        <label className="field field-full">
          <span>管理员账号</span>
          <input
            autoComplete="username"
            onChange={(event) => setUsername(event.target.value)}
            required
            value={username}
          />
        </label>
        <label className="field field-full">
          <span>密码</span>
          <input
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>

        {error && <div className="alert error">{error}</div>}

        <div className="button-row">
          <button className="primary-button" disabled={isLoading} type="submit">
            {isLoading ? "登录中..." : "进入后台"}
          </button>
        </div>
      </form>
    </section>
  );
}

function AdminPolicyManager({
  session,
}: {
  session: AdminSessionResponse;
}) {
  const [statusFilter, setStatusFilter] = useState<AdminPolicyStatus | "">("");
  const [policies, setPolicies] = useState<AdminPolicy[]>([]);
  const [selectedPolicyId, setSelectedPolicyId] = useState<number | null>(null);
  const [newDraft, setNewDraft] = useState<AdminPolicyCreateRequest>({
    title: "",
    content: "",
  });
  const [editor, setEditor] = useState<AdminPolicyUpdateRequest>({
    title: "",
    content: "",
  });
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedPolicy =
    policies.find((policy) => policy.id === selectedPolicyId) ?? null;

  useEffect(() => {
    void loadPolicies();
  }, [session.token, statusFilter]);

  useEffect(() => {
    setEditor({
      title: selectedPolicy?.title ?? "",
      content: selectedPolicy?.content ?? "",
    });
  }, [selectedPolicy?.id, selectedPolicy?.title, selectedPolicy?.content]);

  async function loadPolicies(
    nextSelectedId?: number,
    nextStatusFilter: AdminPolicyStatus | "" = statusFilter,
  ) {
    setIsLoading(true);
    setError(null);
    try {
      const response = await listAdminPolicies(session.token, nextStatusFilter);
      setPolicies(response.policies);
      setSelectedPolicyId((current) => {
        if (nextSelectedId && response.policies.some((item) => item.id === nextSelectedId)) {
          return nextSelectedId;
        }
        if (current && response.policies.some((item) => item.id === current)) {
          return current;
        }
        return response.policies[0]?.id ?? null;
      });
    } catch {
      setError("后台政策列表加载失败，请重新登录或稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = newDraft.title.trim();
    const content = newDraft.content.trim();
    if (!title || !content) {
      setError("请填写政策标题和政策内容。");
      setMessage(null);
      return;
    }

    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const created = await createAdminPolicy(session.token, { title, content });
      setNewDraft({ title: "", content: "" });
      setStatusFilter("");
      setMessage("政策草稿已创建。");
      await loadPolicies(created.id, "");
    } catch {
      setError("政策草稿创建失败，请稍后重试。");
    } finally {
      setIsSaving(false);
    }
  }

  async function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedPolicy) {
      return;
    }

    const title = (editor.title ?? "").trim();
    const content = (editor.content ?? "").trim();
    if (!title || !content) {
      setError("请填写政策标题和政策内容。");
      setMessage(null);
      return;
    }

    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await updateAdminPolicy(session.token, selectedPolicy.id, {
        title,
        content,
      });
      const nextFilter = selectedPolicy.status === "published" ? "" : statusFilter;
      if (selectedPolicy.status === "published") {
        setStatusFilter("");
        setMessage("已创建新版草稿，原发布版本仍保持在线。");
      } else {
        setMessage("政策内容已保存。");
      }
      await loadPolicies(saved.id, nextFilter);
    } catch {
      setError("政策保存失败，请稍后重试。");
    } finally {
      setIsSaving(false);
    }
  }

  async function publishPolicy() {
    if (!selectedPolicy) {
      return;
    }
    if (!window.confirm("发布后会影响客服政策检索结果，请确认。")) {
      return;
    }

    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await publishAdminPolicy(session.token, selectedPolicy.id);
      setStatusFilter("");
      setMessage("政策已发布，知识库已更新。");
      await loadPolicies(response.policy.id, "");
    } catch {
      setError("政策发布失败，请确认向量服务已启动后重试。");
    } finally {
      setIsSaving(false);
    }
  }

  async function disablePolicy() {
    if (!selectedPolicy) {
      return;
    }
    if (!window.confirm("停用后客服端将不再命中该政策，请确认。")) {
      return;
    }

    setIsSaving(true);
    setError(null);
    setMessage(null);
    try {
      const response = await disableAdminPolicy(session.token, selectedPolicy.id);
      setStatusFilter("");
      setMessage("政策已停用，客服端将不再命中该政策。");
      await loadPolicies(response.policy.id, "");
    } catch {
      setError("政策停用失败，请稍后重试。");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="admin-layout">
      <div className="admin-main-stack">
        <div className="panel">
          <div className="panel-heading">
            <div>
              <h2>政策管理</h2>
              <p>{isLoading ? "正在加载..." : `当前显示 ${policies.length} 份政策`}</p>
            </div>
            <div className="button-row inline-actions">
              <button className="secondary-button" onClick={() => void loadPolicies()} type="button">
                刷新
              </button>
            </div>
          </div>

          <div className="filter-row">
            <label className="field compact">
              <span>政策状态</span>
              <select
                onChange={(event) =>
                  setStatusFilter(event.target.value as AdminPolicyStatus | "")
                }
                value={statusFilter}
              >
                <option value="">全部</option>
                {adminPolicyStatusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {error && <div className="alert error">{error}</div>}
          {message && <div className="alert success">{message}</div>}

          <div className="table-wrap admin-policy-table">
            <table>
              <thead>
                <tr>
                  <th>政策标题</th>
                  <th>状态</th>
                  <th>版本</th>
                  <th>更新时间</th>
                  <th>发布时间</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((policy) => (
                  <tr
                    className={policy.id === selectedPolicyId ? "selected-row" : undefined}
                    key={policy.id}
                    onClick={() => setSelectedPolicyId(policy.id)}
                  >
                    <td>{policy.title}</td>
                    <td>
                      <PolicyStatusBadge status={policy.status} />
                    </td>
                    <td>v{policy.version}</td>
                    <td>{formatDate(policy.updated_at)}</td>
                    <td>{formatDate(policy.published_at)}</td>
                  </tr>
                ))}
                {!policies.length && (
                  <tr>
                    <td colSpan={5}>暂无政策</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <form className="panel admin-draft-form" onSubmit={createDraft}>
          <div className="panel-heading">
            <div>
              <h2>新增政策草稿</h2>
              <p>草稿不会进入客服端检索，发布后才会更新知识库。</p>
            </div>
            <button className="primary-button" disabled={isSaving} type="submit">
              创建草稿
            </button>
          </div>
          <div className="admin-form-grid">
            <label className="field">
              <span>政策标题</span>
              <input
                onChange={(event) =>
                  setNewDraft({ ...newDraft, title: event.target.value })
                }
                value={newDraft.title}
              />
            </label>
            <label className="field field-full">
              <span>政策内容</span>
              <textarea
                onChange={(event) =>
                  setNewDraft({ ...newDraft, content: event.target.value })
                }
                rows={5}
                value={newDraft.content}
              />
            </label>
          </div>
        </form>
      </div>

      <aside className="panel admin-detail-panel">
        {selectedPolicy ? (
          <form onSubmit={savePolicy}>
            <div className="panel-heading">
              <div>
                <h2>政策详情</h2>
                <p>
                  {labelPolicyStatus(selectedPolicy.status)} / v{selectedPolicy.version}
                </p>
              </div>
              <PolicyStatusBadge status={selectedPolicy.status} />
            </div>

            <label className="field field-full">
              <span>政策标题</span>
              <input
                onChange={(event) =>
                  setEditor({ ...editor, title: event.target.value })
                }
                value={editor.title ?? ""}
              />
            </label>
            <label className="field field-full">
              <span>政策内容</span>
              <textarea
                onChange={(event) =>
                  setEditor({ ...editor, content: event.target.value })
                }
                rows={12}
                value={editor.content ?? ""}
              />
            </label>

            <div className="button-row">
              <button className="secondary-button" disabled={isSaving} type="submit">
                {selectedPolicy.status === "published" ? "保存为新版草稿" : "保存修改"}
              </button>
              {selectedPolicy.status !== "published" && (
                <button
                  className="primary-button"
                  disabled={isSaving}
                  onClick={() => void publishPolicy()}
                  type="button"
                >
                  发布
                </button>
              )}
              {selectedPolicy.status !== "disabled" && (
                <button
                  className="danger-button"
                  disabled={isSaving}
                  onClick={() => void disablePolicy()}
                  type="button"
                >
                  停用
                </button>
              )}
            </div>

            <div className="summary-box">
              <h3>政策预览</h3>
              <p>{editor.content || "暂无政策内容"}</p>
            </div>
          </form>
        ) : (
          <div className="empty-card compact-empty">
            选择一份政策后可查看详情、编辑草稿、发布或停用。
          </div>
        )}
      </aside>
    </section>
  );
}

function AdminEvaluationComparePage({
  session,
}: {
  session: AdminSessionResponse;
}) {
  const [comparison, setComparison] = useState<AdminEvaluationCompareResponse | null>(
    null,
  );
  const [generationStatus, setGenerationStatus] =
    useState<AdminEvaluationJobStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isStartingGeneration, setIsStartingGeneration] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadComparison();
  }, [session.token]);

  useEffect(() => {
    void loadGenerationStatus();
  }, [session.token]);

  useEffect(() => {
    if (generationStatus?.status !== "running") {
      return;
    }

    const timer = window.setInterval(() => {
      void pollGenerationStatus();
    }, 3000);

    return () => window.clearInterval(timer);
  }, [generationStatus?.status, session.token]);

  async function loadComparison() {
    setIsLoading(true);
    setError(null);
    try {
      setComparison(await getAdminEvaluationCompare(session.token));
    } catch {
      setError("模型效果对比加载失败，请重新登录或稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadGenerationStatus() {
    try {
      setGenerationStatus(
        await getAdminLlmAssistedEvaluationStatus(session.token),
      );
    } catch {
      setGenerationStatus(null);
    }
  }

  async function pollGenerationStatus() {
    try {
      const nextStatus = await getAdminLlmAssistedEvaluationStatus(session.token);
      setGenerationStatus(nextStatus);
      if (nextStatus.status === "succeeded") {
        await loadComparison();
      }
    } catch {
      setGenerationStatus({
        status: "failed",
        message: "增强模式评测状态获取失败，请稍后刷新页面重试。",
        started_at: generationStatus?.started_at ?? null,
        finished_at: null,
        report_generated_at: null,
      });
    }
  }

  async function startLlmAssistedEvaluation() {
    setIsStartingGeneration(true);
    setError(null);
    try {
      const nextStatus = await runAdminLlmAssistedEvaluation(session.token);
      setGenerationStatus(nextStatus);
      if (nextStatus.status === "succeeded") {
        await loadComparison();
      }
    } catch (caughtError) {
      setGenerationStatus({
        status: "failed",
        message:
          caughtError instanceof Error
            ? caughtError.message
            : "增强模式评测启动失败，请稍后重试。",
        started_at: null,
        finished_at: null,
        report_generated_at: null,
      });
    } finally {
      setIsStartingGeneration(false);
    }
  }

  return (
    <section className="eval-layout admin-compare-layout">
      <div className="panel">
        <div className="panel-heading">
          <div>
            <h2>模型效果对比</h2>
            <p>
              {comparison?.rules_report
                ? `规则模式最近质检：${formatDate(comparison.rules_report.generated_at)}`
                : "读取 rules 与增强模式的本地评测报告。"}
            </p>
          </div>
          <div className="compare-actions">
            <button
              className="secondary-button"
              disabled={
                isLoading ||
                isStartingGeneration ||
                generationStatus?.status === "running" ||
                comparison?.llm_status.configured === false
              }
              onClick={() => void startLlmAssistedEvaluation()}
              type="button"
            >
              {generationStatus?.status === "running" || isStartingGeneration
                ? "生成中..."
                : "生成增强评测"}
            </button>
            <button
              className="primary-button"
              disabled={isLoading}
              onClick={() => void loadComparison()}
              type="button"
            >
              {isLoading ? "刷新中..." : "刷新对比"}
            </button>
          </div>
        </div>

        {error && <div className="alert error">{error}</div>}

        {generationStatus && generationStatus.status !== "idle" && (
          <div
            className={
              generationStatus.status === "failed"
                ? "alert error"
                : "health-banner compare-status-banner"
            }
          >
            {generationStatus.message}
          </div>
        )}

        {comparison?.llm_status.fallback_likely && (
          <div className="health-banner warning compare-status-banner">
            <strong>增强模式状态</strong>
            <span>{comparison.llm_status.message}</span>
          </div>
        )}

        {comparison ? (
          <>
            <div className="compare-summary-grid">
              <ModelSummaryCard
                label="规则模式"
                report={comparison.rules_report}
                unavailableText="暂无规则模式评测报告"
              />
              <ModelSummaryCard
                label="增强模式"
                report={comparison.llm_assisted_report}
                unavailableText="暂无增强模式评测报告"
              />
            </div>

            <MetricComparisonTable comparison={comparison} />
          </>
        ) : (
          <div className="empty-card compact-empty">
            {isLoading ? "正在加载模型效果对比..." : "暂无可展示的模型效果对比。"}
          </div>
        )}
      </div>

      {comparison && <IntentComparisonTable comparison={comparison} />}
      {comparison && <FailureDiffSections comparison={comparison} />}
    </section>
  );
}

function ModelSummaryCard({
  label,
  report,
  unavailableText,
}: {
  label: string;
  report: AdminEvaluationReportSummary | null;
  unavailableText: string;
}) {
  if (!report) {
    return (
      <article className="model-summary-card empty">
        <h3>{label}</h3>
        <p>{unavailableText}</p>
      </article>
    );
  }

  return (
    <article className="model-summary-card">
      <div>
        <h3>{label}</h3>
        <p>{formatDate(report.generated_at)}</p>
      </div>
      <div className="model-summary-values">
        <strong>{formatRate(report.passed_cases / report.total_cases)}</strong>
        <span>
          通过 {report.passed_cases}/{report.total_cases}，失败{" "}
          {report.failed_cases_count}
        </span>
        <span>平均响应 {report.metrics.average_latency_ms.toFixed(2)} ms</span>
      </div>
    </article>
  );
}

function MetricComparisonTable({
  comparison,
}: {
  comparison: AdminEvaluationCompareResponse;
}) {
  return (
    <div className="table-wrap compare-table">
      <table>
        <thead>
          <tr>
            <th>指标</th>
            <th>规则模式</th>
            <th>增强模式</th>
            <th>差值</th>
          </tr>
        </thead>
        <tbody>
          {comparisonMetricKeys.map((metric) => (
            <tr key={metric}>
              <td>{labelMetric(metric)}</td>
              <td>{formatComparisonMetric(metric, getComparisonMetricValue(comparison.rules_report, metric))}</td>
              <td>
                {formatComparisonMetric(
                  metric,
                  getComparisonMetricValue(comparison.llm_assisted_report, metric),
                )}
              </td>
              <td>
                <DeltaValue metric={metric} value={comparison.diff_summary.metric_deltas[metric]} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IntentComparisonTable({
  comparison,
}: {
  comparison: AdminEvaluationCompareResponse;
}) {
  const intents = Array.from(
    new Set([
      ...Object.keys(comparison.rules_report?.metrics_by_intent ?? {}),
      ...Object.keys(comparison.llm_assisted_report?.metrics_by_intent ?? {}),
      ...Object.keys(comparison.diff_summary.intent_deltas),
    ]),
  ).sort((left, right) => intentSortValue(left) - intentSortValue(right));

  return (
    <div className="panel table-panel">
      <div className="panel-heading">
        <div>
          <h2>按场景对比</h2>
          <p>{intents.length ? `${intents.length} 个售后场景` : "暂无场景报告"}</p>
        </div>
      </div>

      <div className="table-wrap intent-table">
        <table>
          <thead>
            <tr>
              <th>场景</th>
              <th>规则通过</th>
              <th>增强通过</th>
              <th>识别差值</th>
              <th>流程差值</th>
              <th>政策差值</th>
              <th>平均耗时差值</th>
            </tr>
          </thead>
          <tbody>
            {intents.map((intent) => {
              const rules = comparison.rules_report?.metrics_by_intent[intent];
              const llm = comparison.llm_assisted_report?.metrics_by_intent[intent];
              const deltas = comparison.diff_summary.intent_deltas[intent] ?? {};
              return (
                <tr key={intent}>
                  <td>{labelIntent(intent)}</td>
                  <td>{formatIntentPassCount(rules)}</td>
                  <td>{formatIntentPassCount(llm)}</td>
                  <td><DeltaValue metric="intent_accuracy" value={deltas.intent_accuracy} /></td>
                  <td><DeltaValue metric="tool_call_accuracy" value={deltas.tool_call_accuracy} /></td>
                  <td><DeltaValue metric="policy_hit_rate" value={deltas.policy_hit_rate} /></td>
                  <td><DeltaValue metric="average_latency_ms" value={deltas.average_latency_ms} /></td>
                </tr>
              );
            })}
            {!intents.length && (
              <tr>
                <td colSpan={7}>暂无可对比的场景指标</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FailureDiffSections({
  comparison,
}: {
  comparison: AdminEvaluationCompareResponse;
}) {
  const diff = comparison.diff_summary;
  return (
    <section className="failure-diff-grid">
      <FailureDiffTable
        cases={diff.rules_failed_llm_passed}
        description="规则模式未通过，增强模式通过"
        title="增强改善案例"
      />
      <FailureDiffTable
        cases={diff.llm_failed_rules_passed}
        description="增强模式未通过，规则模式通过"
        title="增强退化案例"
      />
      <FailureDiffTable
        cases={diff.both_failed}
        description="两种模式都未通过"
        title="共同失败案例"
      />
    </section>
  );
}

function FailureDiffTable({
  cases,
  description,
  title,
}: {
  cases: AdminEvaluationCompareResponse["diff_summary"]["rules_failed_llm_passed"];
  description: string;
  title: string;
}) {
  return (
    <div className="panel table-panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{cases.length ? `${description}：${cases.length} 条` : description}</p>
        </div>
      </div>

      <div className="table-wrap compare-failure-table">
        <table>
          <thead>
            <tr>
              <th>案例</th>
              <th>用户问题</th>
              <th>预期场景</th>
              <th>规则判断</th>
              <th>增强判断</th>
              <th>复查原因</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((item) => (
              <tr key={item.id}>
                <td>{item.id}</td>
                <td className="preview-cell">{item.user_message}</td>
                <td>{labelIntent(item.expected_intent)}</td>
                <td>{labelIntent(item.rules_actual_intent)}</td>
                <td>{labelIntent(item.llm_assisted_actual_intent)}</td>
                <td className="failure-cell">
                  {formatComparisonReasons(item.rules_failure_reasons, item.llm_assisted_failure_reasons)}
                </td>
              </tr>
            ))}
            {!cases.length && (
              <tr>
                <td colSpan={6}>暂无案例</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ChatPage({
  lastAgentContext,
  lastAgentRun,
  onResult,
}: {
  lastAgentContext: AgentFeedbackContext | null;
  lastAgentRun: AgentProcessResponse | null;
  onResult: (result: AgentProcessResponse, context: AgentFeedbackContext) => void;
}) {
  const [form, setForm] = useState<AgentProcessRequest>(() => ({
    message: examples[0].message,
    requested_amount: examples[0].requested_amount,
    mode: readSmartAssistPreference() ? "llm_assisted" : "rules",
  }));
  const [result, setResult] = useState<AgentProcessResponse | null>(lastAgentRun);
  const [feedbackContext, setFeedbackContext] =
    useState<AgentFeedbackContext | null>(lastAgentContext);
  const [smartAssistEnabled, setSmartAssistEnabled] = useState(() =>
    readSmartAssistPreference(),
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const payload = compactRequest(form);
      const nextResult = await processAgent(payload);
      const nextContext = feedbackContextFromRequest(payload);
      setResult(nextResult);
      setFeedbackContext(nextContext);
      onResult(nextResult, nextContext);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "处理失败，请稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }

  function setExample(example: (typeof examples)[number]) {
    setForm({
      message: example.message,
      requested_amount: example.requested_amount,
      order_number: "",
      external_id: "",
      ticket_number: "",
      mode: smartAssistEnabled ? "llm_assisted" : "rules",
    });
  }

  function updateSmartAssistPreference(enabled: boolean) {
    setSmartAssistEnabled(enabled);
    setForm((current) => ({
      ...current,
      mode: enabled ? "llm_assisted" : "rules",
    }));
    localStorage.setItem(SMART_ASSIST_PREF_KEY, String(enabled));
  }

  return (
    <section className="page-grid chat-grid">
      <form className="panel form-panel" onSubmit={submit}>
        <div className="panel-heading">
          <div>
            <h2>接待用户问题</h2>
            <p>输入用户原话，系统会给出处理结论、参考政策和回复草稿。</p>
          </div>
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
        </div>

        <label className="field field-full">
          <span>用户问题</span>
          <textarea
            onChange={(event) => setForm({ ...form, message: event.target.value })}
            required
            rows={5}
            value={form.message}
          />
        </label>

        <div className="example-row" aria-label="示例问题">
          {examples.map((example) => (
            <button
              className="example-button"
              key={example.label}
              onClick={() => setExample(example)}
              type="button"
            >
              <strong>{example.label}</strong>
              <span>{example.description}</span>
            </button>
          ))}
        </div>

        <div className="field-grid">
          <label className="field">
            <span>订单号</span>
            <input
              onChange={(event) => setForm({ ...form, order_number: event.target.value })}
              placeholder="ORD-2026-0002"
              value={form.order_number ?? ""}
            />
          </label>
          <label className="field">
            <span>客户编号</span>
            <input
              onChange={(event) => setForm({ ...form, external_id: event.target.value })}
              placeholder="可选"
              value={form.external_id ?? ""}
            />
          </label>
          <label className="field">
            <span>已有工单号</span>
            <input
              onChange={(event) => setForm({ ...form, ticket_number: event.target.value })}
              placeholder="可选"
              value={form.ticket_number ?? ""}
            />
          </label>
          <label className="field">
            <span>期望退款金额</span>
            <input
              min="0"
              onChange={(event) =>
                setForm({ ...form, requested_amount: event.target.value })
              }
              placeholder="50.00"
              step="0.01"
              type="number"
              value={form.requested_amount ?? ""}
            />
          </label>
        </div>

        {error && <div className="alert error">{error}</div>}

        <div className="button-row">
          <button className="primary-button" disabled={isLoading} type="submit">
            {isLoading ? "生成中..." : "生成处理建议"}
          </button>
        </div>
      </form>

      <AgentResultPanel context={feedbackContext} result={result} />
    </section>
  );
}

function AgentResultPanel({
  context,
  result,
}: {
  context: AgentFeedbackContext | null;
  result: AgentProcessResponse | null;
}) {
  if (!result) {
    return (
      <section className="panel empty-panel">
        <h2>处理建议</h2>
        <p>选择示例或输入用户问题后，这里会展示问题类型、处理结论和客服回复。</p>
      </section>
    );
  }

  const modeLabel = result.need_human ? "建议转人工" : "可自动回复";
  const modeTone: BadgeTone = result.need_human ? "warning" : "success";

  return (
    <section className="result-stack">
      <div className="metric-grid">
        <Metric label="问题类型" value={labelIntent(result.intent)} />
        <Metric label="处理方式" tone={modeTone} value={modeLabel} />
        <Metric label="判断置信度" value={`${Math.round(result.confidence * 100)}%`} />
        <Metric label="关联工单" value={result.ticket_id ?? "暂未创建"} />
      </div>

      <div className="panel decision-panel">
        <div className="panel-heading">
          <div>
            <h2>处理结论</h2>
            <p>{describeIntent(result.intent)}</p>
          </div>
          <Badge tone={modeTone}>{modeLabel}</Badge>
        </div>
        <p className="reply-text">{localizeServiceReply(result.reply)}</p>
      </div>

      <PolicySummary sources={result.policy_sources} />

      <AgentFeedbackPanel context={context} result={result} />
    </section>
  );
}

function AgentFeedbackPanel({
  context,
  result,
}: {
  context: AgentFeedbackContext | null;
  result: AgentProcessResponse;
}) {
  const [feedbackType, setFeedbackType] = useState<AgentFeedbackType>("accepted");
  const [finalReply, setFinalReply] = useState("");
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setFeedbackType("accepted");
    setFinalReply("");
    setReason("");
    setSubmitted(false);
    setMessage(null);
    setError(null);
  }, [context, result]);

  async function submitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!context || submitted) {
      return;
    }

    const normalizedFinalReply = finalReply.trim();
    const normalizedReason = reason.trim();
    if (feedbackType === "edited" && !normalizedFinalReply) {
      setError("修改后采纳需要填写客服最终回复。");
      setMessage(null);
      return;
    }
    if (feedbackType === "rejected" && !normalizedReason) {
      setError("不采纳需要填写反馈原因。");
      setMessage(null);
      return;
    }

    const request: AgentFeedbackCreateRequest = {
      message: context.message,
      intent: result.intent,
      ai_reply: result.reply,
      feedback_type: feedbackType,
      ticket_number: result.ticket_id ?? context.ticket_number,
      order_number: context.order_number,
      agent_mode: context.agent_mode,
    };
    if (normalizedFinalReply) {
      request.final_reply = normalizedFinalReply;
    }
    if (normalizedReason) {
      request.reason = normalizedReason;
    }

    setIsSubmitting(true);
    setError(null);
    setMessage(null);
    try {
      await createAgentFeedback(request);
      setSubmitted(true);
      setMessage("反馈已记录，将用于后续质检分析。");
    } catch {
      setError("反馈提交失败，请稍后重试。");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <form className="panel feedback-panel" onSubmit={submitFeedback}>
      <div className="panel-heading">
        <div>
          <h2>人工反馈</h2>
          <p>{submitted ? "本次处理建议已完成反馈。" : "记录客服对本次建议的处理判断。"}</p>
        </div>
        {submitted && <Badge tone="success">已反馈</Badge>}
      </div>

      {!context ? (
        <div className="empty-card compact-empty">重新生成处理建议后可记录人工反馈。</div>
      ) : (
        <>
          <div className="feedback-options" aria-label="反馈类型">
            {feedbackOptions.map((option) => (
              <button
                aria-pressed={feedbackType === option.value}
                className={
                  feedbackType === option.value
                    ? "feedback-option active"
                    : "feedback-option"
                }
                disabled={isSubmitting || submitted}
                key={option.value}
                onClick={() => {
                  setFeedbackType(option.value);
                  setError(null);
                  setMessage(null);
                }}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>

          {feedbackType === "accepted" && (
            <div className="feedback-note">将记录客服采纳了本次建议。</div>
          )}

          {(feedbackType === "edited" || feedbackType === "rejected") && (
            <label className="field field-full">
              <span>
                {feedbackType === "edited" ? "客服最终回复" : "客服最终回复（可选）"}
              </span>
              <textarea
                disabled={isSubmitting || submitted}
                onChange={(event) => setFinalReply(event.target.value)}
                rows={4}
                value={finalReply}
              />
            </label>
          )}

          {(feedbackType === "edited" || feedbackType === "rejected") && (
            <label className="field field-full">
              <span>{feedbackType === "rejected" ? "反馈原因" : "修改原因（可选）"}</span>
              <textarea
                disabled={isSubmitting || submitted}
                maxLength={500}
                onChange={(event) => setReason(event.target.value)}
                rows={3}
                value={reason}
              />
            </label>
          )}

          {error && <div className="alert error">{error}</div>}
          {message && <div className="alert success">{message}</div>}

          <div className="button-row">
            <button
              className="primary-button"
              disabled={isSubmitting || submitted}
              type="submit"
            >
              {submitted ? "已反馈" : isSubmitting ? "提交中..." : "提交反馈"}
            </button>
          </div>
        </>
      )}
    </form>
  );
}

function TicketsPage() {
  const [filters, setFilters] = useState<TicketFilters>({ page: 1, page_size: 10 });
  const [pagination, setPagination] = useState({
    total: 0,
    page: 1,
    pageSize: 10,
    totalPages: 1,
  });
  const [tickets, setTickets] = useState<TicketListItem[]>([]);
  const [selectedTicket, setSelectedTicket] = useState<TicketDetail | null>(null);
  const [selectedNumber, setSelectedNumber] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadTickets(filters);
  }, [filters.status, filters.category, filters.priority, filters.page, filters.page_size]);

  async function loadTickets(nextFilters: TicketFilters) {
    setIsLoading(true);
    setError(null);
    try {
      const response = await listTickets(nextFilters);
      setTickets(response.tickets);
      setPagination({
        total: response.total,
        page: response.page,
        pageSize: response.page_size,
        totalPages: response.total_pages,
      });
      const selectedTicketIsVisible = response.tickets.some(
        (ticket) => ticket.ticket_number === selectedNumber,
      );
      if (selectedNumber && selectedTicketIsVisible) {
        return;
      }
      if (response.tickets[0]) {
        void loadTicketDetail(response.tickets[0].ticket_number);
      } else {
        setSelectedNumber(null);
        setSelectedTicket(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "工单加载失败，请稍后重试。");
    } finally {
      setIsLoading(false);
    }
  }

  function updateTicketFilters(nextValues: Partial<TicketFilters>) {
    setFilters((current) => ({
      ...current,
      ...nextValues,
      page: 1,
    }));
  }

  function updateTicketPageSize(value: number) {
    const nextPageSize = Math.max(1, Math.min(100, value || 1));
    setFilters((current) => ({
      ...current,
      page: 1,
      page_size: nextPageSize,
    }));
  }

  function goToTicketPage(nextPage: number) {
    const boundedPage = Math.max(1, Math.min(pagination.totalPages, nextPage));
    setFilters((current) => ({
      ...current,
      page: boundedPage,
    }));
  }

  async function loadTicketDetail(ticketNumber: string) {
    setSelectedNumber(ticketNumber);
    setError(null);
    try {
      setSelectedTicket(await getTicket(ticketNumber));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "工单详情加载失败。");
    }
  }

  async function refreshSelectedTicket(ticketNumber: string) {
    await Promise.all([loadTicketDetail(ticketNumber), loadTickets(filters)]);
  }

  return (
    <section className="ticket-layout">
      <div className="panel table-panel">
        <div className="panel-heading">
          <div>
            <h2>工单队列</h2>
            <p>
              {isLoading
                ? "正在加载..."
                : `当前显示 ${tickets.length} / ${pagination.total} 条工单`}
            </p>
          </div>
        </div>

        <div className="filter-row">
          <SelectField
            label="状态"
            onChange={(value) => updateTicketFilters({ status: value || undefined })}
            options={statusOptions}
            value={filters.status ?? ""}
          />
          <SelectField
            label="问题类型"
            onChange={(value) => updateTicketFilters({ category: value || undefined })}
            options={categoryOptions}
            value={filters.category ?? ""}
          />
          <SelectField
            label="优先级"
            onChange={(value) => updateTicketFilters({ priority: value || undefined })}
            options={priorityOptions}
            value={filters.priority ?? ""}
          />
          <label className="field compact">
            <span>每页数量</span>
            <input
              min={1}
              max={100}
              onChange={(event) => updateTicketPageSize(Number(event.target.value))}
              type="number"
              value={filters.page_size ?? pagination.pageSize}
            />
          </label>
        </div>

        {error && <div className="alert error">{error}</div>}

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>工单号</th>
                <th>关联订单</th>
                <th>问题类型</th>
                <th>优先级</th>
                <th>状态</th>
                <th>处理队列</th>
                <th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((ticket) => (
                <tr
                  className={
                    ticket.ticket_number === selectedNumber ? "selected-row" : undefined
                  }
                  key={ticket.ticket_number}
                  onClick={() => void loadTicketDetail(ticket.ticket_number)}
                >
                  <td>{ticket.ticket_number}</td>
                  <td>{ticket.order_number}</td>
                  <td>{labelCategory(ticket.category)}</td>
                  <td>
                    <PriorityBadge priority={ticket.priority} />
                  </td>
                  <td>
                    <StatusBadge status={ticket.status} />
                  </td>
                  <td>{ticket.is_escalated ? "人工处理" : "AI 预处理"}</td>
                  <td>{formatDate(ticket.created_at)}</td>
                </tr>
              ))}
              {!tickets.length && !isLoading && (
                <tr>
                  <td colSpan={7}>暂无符合条件的工单</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="pagination-row" aria-label="工单分页">
          <span className="pagination-summary">
            第 {pagination.page} / {pagination.totalPages} 页
          </span>
          <div className="pagination-buttons">
            <button
              className="secondary-button"
              disabled={isLoading || pagination.page <= 1}
              onClick={() => goToTicketPage(pagination.page - 1)}
              type="button"
            >
              上一页
            </button>
            <button
              className="secondary-button"
              disabled={isLoading || pagination.page >= pagination.totalPages}
              onClick={() => goToTicketPage(pagination.page + 1)}
              type="button"
            >
              下一页
            </button>
          </div>
        </div>
      </div>

      <TicketDetailPanel onSaved={refreshSelectedTicket} ticket={selectedTicket} />
    </section>
  );
}

function TicketDetailPanel({
  ticket,
  onSaved,
}: {
  ticket: TicketDetail | null;
  onSaved: (ticketNumber: string) => Promise<void>;
}) {
  const [status, setStatus] = useState("");
  const [resolution, setResolution] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setStatus(ticket?.status ?? "");
    setResolution(ticket?.resolution ?? "");
  }, [ticket?.ticket_number, ticket?.status, ticket?.resolution]);

  useEffect(() => {
    setMessage(null);
    setSaveError(null);
  }, [ticket?.ticket_number]);

  if (!ticket) {
    return (
      <aside className="panel detail-panel">
        <h2>工单详情</h2>
        <p className="muted">请选择一条工单查看完整处理信息。</p>
      </aside>
    );
  }

  const activeTicket = ticket;

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextResolution = resolution.trim();
    if ((status === "resolved" || status === "closed") && !nextResolution) {
      setSaveError("已解决或已关闭的工单需要填写处理备注。");
      setMessage(null);
      return;
    }

    setIsSaving(true);
    setSaveError(null);
    setMessage(null);
    try {
      const request: TicketStatusUpdateRequest = {
        status,
        resolution: nextResolution,
      };
      await updateTicketStatus(activeTicket.ticket_number, request);
      await onSaved(activeTicket.ticket_number);
      setMessage("处理结果已保存。");
    } catch {
      setSaveError("处理结果保存失败，请稍后重试。");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <aside className="panel detail-panel">
      <div className="panel-heading">
        <div>
          <h2>{activeTicket.ticket_number}</h2>
          <p>{activeTicket.subject}</p>
        </div>
        <StatusBadge status={activeTicket.status} />
      </div>

      <dl className="detail-list">
        <DetailItem label="关联订单" value={activeTicket.order_number} />
        <DetailItem label="客户" value={activeTicket.user_summary.name} />
        <DetailItem label="问题类型" value={labelCategory(activeTicket.category)} />
        <DetailItem label="优先级" value={labelPriority(activeTicket.priority)} />
        <DetailItem label="创建时间" value={formatDate(activeTicket.created_at)} />
        <DetailItem label="更新时间" value={formatDate(activeTicket.updated_at)} />
      </dl>

      <div className="text-block">
        <h3>问题描述</h3>
        <p>{activeTicket.description}</p>
      </div>
      <div className="text-block">
        <h3>处理结果</h3>
        <p>{activeTicket.resolution ?? "暂未填写处理结果"}</p>
      </div>

      <form className="ticket-resolution-form" onSubmit={handleSave}>
        <div className="ticket-resolution-header">
          <h3>人工处理</h3>
          <button className="primary-button" disabled={isSaving} type="submit">
            {isSaving ? "保存中..." : "保存处理结果"}
          </button>
        </div>
        <label className="field">
          <span>当前状态</span>
          <select onChange={(event) => setStatus(event.target.value)} value={status}>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>处理备注</span>
          <textarea
            maxLength={1000}
            onChange={(event) => setResolution(event.target.value)}
            placeholder="填写本次处理结果、沟通结论或后续跟进说明"
            rows={5}
            value={resolution}
          />
        </label>
        <div className="form-footnote">
          <span>已解决或已关闭时必须填写处理备注。</span>
          <span>{resolution.trim().length}/1000</span>
        </div>
        {saveError && <div className="alert error">{saveError}</div>}
        {message && <div className="alert success">{message}</div>}
      </form>

      <div className="summary-box">
        <h3>关联订单</h3>
        <dl className="detail-list compact-list">
          <DetailItem
            label="订单状态"
            value={labelOrderStatus(activeTicket.order_summary.status)}
          />
          <DetailItem
            label="支付状态"
            value={labelPaymentStatus(activeTicket.order_summary.payment_status)}
          />
          <DetailItem label="订单金额" value={`¥${activeTicket.order_summary.total_amount}`} />
          <DetailItem label="会员等级" value={activeTicket.user_summary.tier} />
        </dl>
      </div>
    </aside>
  );
}

function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [query, setQuery] = useState("七天内不想要了可以退吗");
  const [topK, setTopK] = useState(3);
  const [results, setResults] = useState<PolicySearchResult[]>([]);
  const [isLoadingDocs, setIsLoadingDocs] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedDocument, setSelectedDocument] =
    useState<KnowledgeDocument | null>(null);

  useEffect(() => {
    async function loadDocuments() {
      setIsLoadingDocs(true);
      setError(null);
      try {
        const response = await listKnowledgeDocuments();
        setDocuments(response.documents);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "政策知识库加载失败。");
      } finally {
        setIsLoadingDocs(false);
      }
    }

    void loadDocuments();
  }, []);

  useEffect(() => {
    if (!selectedDocument) {
      return;
    }

    const previousBodyOverflow = document.body.style.overflow;
    const previousBodyOverscrollBehavior = document.body.style.overscrollBehavior;
    document.body.style.overflow = "hidden";
    document.body.style.overscrollBehavior = "none";

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedDocument(null);
      }
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousBodyOverflow;
      document.body.style.overscrollBehavior = previousBodyOverscrollBehavior;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [selectedDocument]);

  async function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSearching(true);
    setError(null);
    try {
      const response = await searchPolicies(query, topK);
      setResults(response.results);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "政策检索失败。");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <section className="knowledge-layout">
      <div className="panel">
        <div className="panel-heading">
          <div>
            <h2>政策文档</h2>
            <p>{isLoadingDocs ? "正在加载..." : `已收录 ${documents.length} 份政策`}</p>
          </div>
        </div>

        {error && <div className="alert error">{error}</div>}

        <div className="policy-card-grid">
          {documents.map((document) => (
            <article
              aria-label={`查看${document.policy_title}`}
              className="policy-card policy-card-button"
              key={document.source_file}
              onClick={() => setSelectedDocument(document)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setSelectedDocument(document);
                }
              }}
              role="button"
              tabIndex={0}
            >
              <div>
                <Badge tone="neutral">{policyScenario(document.policy_title, document.source_file)}</Badge>
                <h3>{document.policy_title}</h3>
              </div>
              <p>{document.preview}</p>
              <div className="policy-meta">
                <span>约 {document.character_count} 字</span>
                <span>{policyScenario(document.policy_title, document.source_file)}</span>
              </div>
            </article>
          ))}
          {!documents.length && !isLoadingDocs && (
            <div className="empty-card">暂无政策文档</div>
          )}
        </div>
      </div>

      <div className="panel search-panel">
        <div className="panel-heading">
          <div>
            <h2>政策检索</h2>
            <p>输入用户问题，验证系统会引用哪些售后政策。</p>
          </div>
        </div>

        <form className="search-form" onSubmit={submitSearch}>
          <label className="field field-full">
            <span>用户问题</span>
            <input
              onChange={(event) => setQuery(event.target.value)}
              required
              value={query}
            />
          </label>
          <label className="field compact">
            <span>返回条数</span>
            <input
              min={1}
              max={10}
              onChange={(event) => setTopK(Number(event.target.value))}
              type="number"
              value={topK}
            />
          </label>
          <button className="primary-button" disabled={isSearching} type="submit">
            {isSearching ? "检索中..." : "检索政策"}
          </button>
        </form>

        <div className="result-list">
          {results.map((result, index) => (
            <article className="search-result" key={`${result.source_file}-${index}`}>
              <div>
                <strong>{result.policy_title}</strong>
                <span>匹配度 {formatScore(result.score)}</span>
              </div>
              <p>{result.matched_text}</p>
            </article>
          ))}
          {!results.length && (
            <div className="empty-card">输入问题后会展示命中的政策片段。</div>
          )}
        </div>
      </div>

      {selectedDocument && (
        <div
          className="modal-backdrop"
          onClick={() => setSelectedDocument(null)}
          role="presentation"
        >
          <section
            aria-labelledby="policy-modal-title"
            aria-modal="true"
            className="policy-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="policy-modal-header">
              <div>
                <Badge tone="neutral">
                  {policyScenario(
                    selectedDocument.policy_title,
                    selectedDocument.source_file,
                  )}
                </Badge>
                <h2 id="policy-modal-title">{selectedDocument.policy_title}</h2>
                <p>约 {selectedDocument.character_count} 字</p>
              </div>
              <button
                className="secondary-button"
                onClick={() => setSelectedDocument(null)}
                type="button"
              >
                关闭
              </button>
            </div>
            <div className="policy-modal-content" tabIndex={0}>
              {selectedDocument.content}
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

function EvaluationPage() {
  const [report, setReport] = useState<LatestEvaluationResponse | null>(null);
  const [history, setHistory] = useState<EvaluationHistoryItem[]>([]);
  const [feedbackSummary, setFeedbackSummary] =
    useState<FeedbackSummaryResponse | null>(null);
  const [selectedFailure, setSelectedFailure] = useState<EvaluationCaseResult | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadReport();
  }, []);

  async function loadReport() {
    setIsLoading(true);
    setError(null);
    try {
      const [latestReport, historyResponse, feedbackResponse] = await Promise.all([
        getLatestEvaluation(),
        getEvaluationHistory(12),
        getFeedbackSummary(),
      ]);
      setReport(latestReport);
      setHistory(historyResponse.reports);
      setFeedbackSummary(feedbackResponse);
      setSelectedFailure((current) => {
        if (!latestReport.failed_cases.length) {
          return null;
        }
        return (
          latestReport.failed_cases.find((item) => item.id === current?.id) ??
          latestReport.failed_cases[0]
        );
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "质检报告加载失败。");
    } finally {
      setIsLoading(false);
    }
  }

  if (!report && !isLoading) {
    return (
      <section className="panel empty-panel">
        <div className="panel-heading">
          <div>
            <h2>质检报告</h2>
            <p>暂无可展示的质检报告。</p>
          </div>
          <button className="primary-button" onClick={() => void loadReport()} type="button">
            刷新报告
          </button>
        </div>
        {error && <div className="alert error">{error}</div>}
      </section>
    );
  }

  return (
    <section className="eval-layout">
      <div className="panel">
        <div className="panel-heading">
          <div>
            <h2>总体质量</h2>
            <p>{report ? `最近质检：${formatDate(report.generated_at)}` : "正在加载..."}</p>
          </div>
          <button
            className="primary-button"
            disabled={isLoading}
            onClick={() => void loadReport()}
            type="button"
          >
            {isLoading ? "刷新中..." : "刷新报告"}
          </button>
        </div>

        {error && <div className="alert error">{error}</div>}

        {report && (
          <>
            <QualityHealthBanner report={report} />

            <div className="eval-summary-grid">
              <Metric
                label="总体通过率"
                tone={report.failed_cases_count === 0 ? "success" : "warning"}
                value={formatRate(report.passed_cases / report.total_cases)}
              />
              <Metric label="通过用例" value={`${report.passed_cases}/${report.total_cases}`} />
              <Metric label="需复查案例" value={String(report.failed_cases_count)} />
              <Metric
                label="平均响应"
                value={`${report.metrics.average_latency_ms.toFixed(2)} ms`}
              />
            </div>

            <div className="eval-metric-grid">
              {Object.entries(report.metrics).map(([metric, value]) => (
                <Metric
                  key={metric}
                  label={labelMetric(metric)}
                  value={
                    metric === "average_latency_ms"
                      ? `${value.toFixed(2)} ms`
                      : formatRate(value)
                  }
                />
              ))}
            </div>

            <div className="eval-small-metric-grid">
              <Metric
                label="P50 响应耗时"
                value={`${report.latency_percentiles.p50_ms.toFixed(2)} ms`}
              />
              <Metric
                label="P95 响应耗时"
                value={`${report.latency_percentiles.p95_ms.toFixed(2)} ms`}
              />
              <Metric
                label="最慢响应"
                value={`${report.latency_percentiles.max_ms.toFixed(2)} ms`}
              />
            </div>

            <FailureReasonCounts counts={report.failure_reason_counts} />
          </>
        )}
      </div>

      <HistoryTrendTable history={history} />

      {feedbackSummary && <FeedbackSummaryPanel summary={feedbackSummary} />}

      {report && <IntentMetricsTable metricsByIntent={report.metrics_by_intent} />}

      {report && (
        <section className="eval-detail-layout">
          <div className="panel table-panel">
            <div className="panel-heading">
              <div>
                <h2>失败案例回放</h2>
                <p>
                  {report.failed_cases.length
                    ? `需要复查 ${report.failed_cases.length} 条`
                    : "当前没有失败案例"}
                </p>
              </div>
            </div>

            {report.failed_cases.length ? (
              <div className="table-wrap eval-failure-table">
                <table>
                  <thead>
                    <tr>
                      <th>案例</th>
                      <th>用户问题</th>
                      <th>预期场景</th>
                      <th>实际判断</th>
                      <th>人工判断</th>
                      <th>复查原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.failed_cases.map((item) => (
                      <tr
                        className={item.id === selectedFailure?.id ? "selected-row" : undefined}
                        key={item.id}
                        onClick={() => setSelectedFailure(item)}
                      >
                        <td>{item.id}</td>
                        <td className="preview-cell">{item.user_message}</td>
                        <td>{labelIntent(item.expected_intent)}</td>
                        <td>{labelIntent(item.actual_intent)}</td>
                        <td>{item.actual_need_human ? "需要人工" : "无需人工"}</td>
                        <td className="failure-cell">
                          {item.failure_reasons.map(labelFailureReason).join("、")}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="success-state">
                <h3>核心场景全部通过</h3>
                <p>本次质检没有失败案例，退款、物流、发票、投诉、账号等场景均通过预期检查。</p>
              </div>
            )}
          </div>

          <FailureCaseDetail item={selectedFailure} />
        </section>
      )}
    </section>
  );
}

function QualityHealthBanner({ report }: { report: LatestEvaluationResponse }) {
  if (report.failed_cases_count === 0) {
    return (
      <div className="health-banner success">
        <strong>当前质量稳定</strong>
        <span>本次 {report.total_cases} 条质检用例全部通过，当前自动处理表现稳定。</span>
      </div>
    );
  }

  return (
    <div className="health-banner warning">
      <strong>存在待复查案例</strong>
      <span>本次有 {report.failed_cases_count} 条案例未通过，请优先查看失败案例回放。</span>
    </div>
  );
}

function FailureReasonCounts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (!entries.length) {
    return (
      <div className="reason-strip">
        <span className="badge success">暂无失败原因</span>
      </div>
    );
  }

  return (
    <div className="reason-strip">
      {entries.map(([reason, count]) => (
        <span className="reason-pill" key={reason}>
          {labelFailureReason(reason)}
          <strong>{count}</strong>
        </span>
      ))}
    </div>
  );
}

function FeedbackSummaryPanel({ summary }: { summary: FeedbackSummaryResponse }) {
  const reasonEntries = Object.entries(summary.reason_counts);

  return (
    <div className="panel feedback-summary-panel">
      <div className="panel-heading">
        <div>
          <h2>人工反馈</h2>
          <p>
            {summary.total
              ? `已沉淀 ${summary.total} 条客服反馈`
              : "暂无人工反馈，客服提交后将在这里汇总。"}
          </p>
        </div>
      </div>

      <div className="eval-summary-grid">
        <Metric label="总反馈数" value={String(summary.total)} />
        <Metric
          label="采纳率"
          tone={summary.accepted_rate >= 0.8 && summary.total ? "success" : undefined}
          value={formatRate(summary.accepted_rate)}
        />
        <Metric label="修改后采纳率" value={formatRate(summary.edited_rate)} />
        <Metric
          label="不采纳率"
          tone={summary.rejected_rate > 0.2 ? "warning" : undefined}
          value={formatRate(summary.rejected_rate)}
        />
      </div>

      {summary.total ? (
        <>
          <div className="feedback-count-row">
            <span>{labelFeedbackType("accepted")} {summary.accepted_count}</span>
            <span>{labelFeedbackType("edited")} {summary.edited_count}</span>
            <span>{labelFeedbackType("rejected")} {summary.rejected_count}</span>
          </div>

          <div className="panel-subsection">
            <h3>常见反馈原因</h3>
            {reasonEntries.length ? (
              <div className="reason-strip">
                {reasonEntries.map(([reason, count]) => (
                  <span className="reason-pill" key={reason}>
                    {reason}
                    <strong>{count}</strong>
                  </span>
                ))}
              </div>
            ) : (
              <p className="muted">暂无原因记录。</p>
            )}
          </div>

          <div className="panel-subsection">
            <h3>最近反馈样本</h3>
            <div className="table-wrap feedback-sample-table">
              <table>
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>反馈</th>
                    <th>用户问题摘要</th>
                    <th>原因</th>
                    <th>最终回复摘要</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.recent_feedback.map((item) => (
                    <tr key={item.id}>
                      <td>{formatDate(item.created_at)}</td>
                      <td>{labelFeedbackType(item.feedback_type)}</td>
                      <td className="preview-cell">{item.message_preview}</td>
                      <td>{item.reason ?? "-"}</td>
                      <td className="preview-cell">
                        {item.final_reply_preview ?? "采纳原回复"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : (
        <div className="empty-card compact-empty">
          暂无人工反馈，客服提交后将在这里汇总。
        </div>
      )}
    </div>
  );
}

function HistoryTrendTable({ history }: { history: EvaluationHistoryItem[] }) {
  return (
    <div className="panel table-panel">
      <div className="panel-heading">
        <div>
          <h2>历史趋势</h2>
          <p>{history.length ? `最近 ${history.length} 次质检` : "暂无历史质检"}</p>
        </div>
      </div>

      <div className="table-wrap history-table">
        <table>
          <thead>
            <tr>
              <th>生成时间</th>
              <th>通过率</th>
              <th>政策命中</th>
              <th>失败数</th>
              <th>平均耗时</th>
              <th>P95 耗时</th>
            </tr>
          </thead>
          <tbody>
            {history.map((item) => (
              <tr key={item.report_file}>
                <td>{formatDate(item.generated_at)}</td>
                <td>
                  <TrendValue value={item.passed_cases / item.total_cases} />
                </td>
                <td>
                  <TrendValue value={item.metrics.policy_hit_rate} />
                </td>
                <td>{item.failed_cases}</td>
                <td>{item.metrics.average_latency_ms.toFixed(2)} ms</td>
                <td>{item.latency_percentiles.p95_ms.toFixed(2)} ms</td>
              </tr>
            ))}
            {!history.length && (
              <tr>
                <td colSpan={6}>暂无历史质检</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IntentMetricsTable({
  metricsByIntent,
}: {
  metricsByIntent: LatestEvaluationResponse["metrics_by_intent"];
}) {
  const rows = Object.entries(metricsByIntent).sort(
    ([left], [right]) => intentSortValue(left) - intentSortValue(right),
  );

  return (
    <div className="panel table-panel">
      <div className="panel-heading">
        <div>
          <h2>按场景质量</h2>
          <p>{rows.length} 个售后场景</p>
        </div>
      </div>

      <div className="table-wrap intent-table">
        <table>
          <thead>
            <tr>
              <th>场景</th>
              <th>用例数</th>
              <th>通过</th>
              <th>复查</th>
              <th>识别准确</th>
              <th>流程匹配</th>
              <th>政策命中</th>
              <th>平均耗时</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([intent, item]) => (
              <tr key={intent}>
                <td>{labelIntent(intent)}</td>
                <td>{item.total_cases}</td>
                <td>{item.passed_cases}</td>
                <td>{item.failed_cases}</td>
                <td>{formatRate(item.metrics.intent_accuracy)}</td>
                <td>{formatRate(item.metrics.tool_call_accuracy)}</td>
                <td>{formatRate(item.metrics.policy_hit_rate)}</td>
                <td>{item.metrics.average_latency_ms.toFixed(2)} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FailureCaseDetail({ item }: { item: EvaluationCaseResult | null }) {
  if (!item) {
    return (
      <aside className="panel failure-detail-panel">
        <h2>回放详情</h2>
        <p className="muted">当前没有失败案例需要复查。</p>
      </aside>
    );
  }

  return (
    <aside className="panel failure-detail-panel">
      <div className="panel-heading">
        <div>
          <h2>{item.id}</h2>
          <p>
            {labelIntent(item.expected_intent)} / 实际判断为 {labelIntent(item.actual_intent)}
          </p>
        </div>
        <Badge tone={item.policy_hit ? "success" : "danger"}>
          {item.policy_hit ? "政策已命中" : "政策未命中"}
        </Badge>
      </div>

      <dl className="detail-list">
        <DetailItem
          label="人工判断"
          value={item.actual_need_human ? "需要人工协助" : "无需人工协助"}
        />
        <DetailItem label="响应耗时" value={`${item.latency_ms.toFixed(2)} ms`} />
        <DetailItem label="复查原因" value={item.failure_reasons.map(labelFailureReason).join("、")} />
      </dl>

      <div className="text-block">
        <h3>用户问题</h3>
        <p>{item.user_message}</p>
      </div>

      <div className="text-block">
        <h3>客服回复</h3>
        <p className="reply-text">{localizeServiceReply(item.reply)}</p>
      </div>

      <div className="text-block">
        <h3>引用政策</h3>
        <PolicySummary sources={item.actual_policy_sources} compact />
      </div>
    </aside>
  );
}

function PolicySummary({
  sources,
  compact = false,
}: {
  sources: AgentProcessResponse["policy_sources"];
  compact?: boolean;
}) {
  if (!sources.length) {
    return (
      <div className={compact ? "empty-card compact-empty" : "panel empty-panel small-empty"}>
        暂无参考政策
      </div>
    );
  }

  return (
    <div className={compact ? "policy-summary compact-policy" : "panel policy-summary"}>
      {!compact && (
        <div className="panel-heading">
          <div>
            <h2>参考政策</h2>
            <p>用于支撑本次处理建议的售后规则。</p>
          </div>
        </div>
      )}
      <div className="policy-list">
        {sources.map((source) => (
          <article className="policy-mini-card" key={`${source.source_file}-${source.policy_title}`}>
            <div>
              <strong>{source.policy_title}</strong>
              <span>{policyScenario(source.policy_title, source.source_file)}</span>
            </div>
            <Badge tone="neutral">匹配度 {formatScore(source.score)}</Badge>
          </article>
        ))}
      </div>
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="field compact">
      <span>{label}</span>
      <select onChange={(event) => onChange(event.target.value)} value={value}>
        <option value="">全部</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: BadgeTone;
}) {
  return (
    <div className={tone ? `metric metric-${tone}` : "metric"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value || "-"}</dd>
    </>
  );
}

function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTone(status)}>{labelStatus(status)}</Badge>;
}

function PolicyStatusBadge({ status }: { status: AdminPolicyStatus }) {
  return <Badge tone={policyStatusTone(status)}>{labelPolicyStatus(status)}</Badge>;
}

function PriorityBadge({ priority }: { priority: string }) {
  return <Badge tone={priorityTone(priority)}>{labelPriority(priority)}</Badge>;
}

function compactRequest(request: AgentProcessRequest): AgentProcessRequest {
  return Object.fromEntries(
    Object.entries(request).filter(([, value]) => value !== undefined && value !== ""),
  ) as AgentProcessRequest;
}

function feedbackContextFromRequest(request: AgentProcessRequest): AgentFeedbackContext {
  return {
    message: request.message,
    order_number: request.order_number,
    ticket_number: request.ticket_number,
    agent_mode: request.mode ?? "rules",
  };
}

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatRate(value: number): string {
  if (!Number.isFinite(value)) {
    return "-";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function getComparisonMetricValue(
  report: AdminEvaluationReportSummary | null,
  metric: string,
): number | null {
  if (!report) {
    return null;
  }
  switch (metric) {
    case "intent_accuracy":
      return report.metrics.intent_accuracy;
    case "tool_call_accuracy":
      return report.metrics.tool_call_accuracy;
    case "policy_hit_rate":
      return report.metrics.policy_hit_rate;
    case "human_escalation_accuracy":
      return report.metrics.human_escalation_accuracy;
    case "auto_resolution_rate":
      return report.metrics.auto_resolution_rate;
    case "average_latency_ms":
      return report.metrics.average_latency_ms;
    case "p50_ms":
      return report.latency_percentiles.p50_ms;
    case "p95_ms":
      return report.latency_percentiles.p95_ms;
    case "max_ms":
      return report.latency_percentiles.max_ms;
    case "total_cases":
      return report.total_cases;
    case "passed_cases":
      return report.passed_cases;
    case "failed_cases_count":
      return report.failed_cases_count;
    default:
      return null;
  }
}

function formatComparisonMetric(metric: string, value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return "-";
  }
  if (isRateMetric(metric)) {
    return formatRate(value);
  }
  if (isLatencyMetric(metric)) {
    return `${value.toFixed(2)} ms`;
  }
  return String(Math.round(value));
}

function DeltaValue({
  metric,
  value,
}: {
  metric: string;
  value: number | undefined;
}) {
  if (value === undefined || !Number.isFinite(value)) {
    return <span className="delta-value neutral">-</span>;
  }
  return (
    <span className={`delta-value ${deltaTone(metric, value)}`}>
      {formatComparisonDelta(metric, value)}
    </span>
  );
}

function formatComparisonDelta(metric: string, value: number): string {
  if (value === 0) {
    return "0";
  }
  const sign = value > 0 ? "+" : "";
  if (isRateMetric(metric)) {
    return `${sign}${(value * 100).toFixed(1)} 个百分点`;
  }
  if (isLatencyMetric(metric)) {
    return `${sign}${value.toFixed(2)} ms`;
  }
  return `${sign}${Math.round(value)}`;
}

function deltaTone(metric: string, value: number): "positive" | "negative" | "neutral" {
  if (value === 0 || metric === "total_cases") {
    return "neutral";
  }
  if (isLatencyMetric(metric) || metric === "failed_cases_count") {
    return value < 0 ? "positive" : "negative";
  }
  return value > 0 ? "positive" : "negative";
}

function isRateMetric(metric: string): boolean {
  return metric.endsWith("_accuracy") || metric.endsWith("_rate");
}

function isLatencyMetric(metric: string): boolean {
  return metric === "average_latency_ms" || metric.endsWith("_ms");
}

function formatIntentPassCount(
  item: AdminEvaluationReportSummary["metrics_by_intent"][string] | undefined,
): string {
  return item ? `${item.passed_cases}/${item.total_cases}` : "-";
}

function formatComparisonReasons(
  rulesReasons: string[],
  llmReasons: string[],
): string {
  const rules = rulesReasons.length
    ? rulesReasons.map(labelFailureReason).join("、")
    : "通过";
  const llm = llmReasons.length
    ? llmReasons.map(labelFailureReason).join("、")
    : "通过";
  return `规则：${rules}；增强：${llm}`;
}

function formatScore(value: number): string {
  if (!Number.isFinite(value)) {
    return "-";
  }
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.max(0, Math.min(100, normalized)).toFixed(0)}%`;
}

function TrendValue({ value }: { value: number }) {
  const bounded = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  return (
    <span className="trend-value">
      <span className="trend-bar" aria-hidden="true">
        <span style={{ width: `${bounded * 100}%` }} />
      </span>
      <span>{formatRate(value)}</span>
    </span>
  );
}

function readLastAgentRun(): AgentProcessResponse | null {
  try {
    const value = localStorage.getItem(LAST_AGENT_RUN_KEY);
    return value ? (JSON.parse(value) as AgentProcessResponse) : null;
  } catch {
    return null;
  }
}

function readLastAgentContext(): AgentFeedbackContext | null {
  try {
    const value = localStorage.getItem(LAST_AGENT_CONTEXT_KEY);
    return value ? (JSON.parse(value) as AgentFeedbackContext) : null;
  } catch {
    return null;
  }
}

function readSmartAssistPreference(): boolean {
  try {
    return localStorage.getItem(SMART_ASSIST_PREF_KEY) === "true";
  } catch {
    return false;
  }
}

function readAdminSession(): AdminSessionResponse | null {
  try {
    const value = localStorage.getItem(ADMIN_SESSION_KEY);
    if (!value) {
      return null;
    }
    const session = JSON.parse(value) as AdminSessionResponse;
    if (!session.token || new Date(session.expires_at).getTime() <= Date.now()) {
      localStorage.removeItem(ADMIN_SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export default App;
