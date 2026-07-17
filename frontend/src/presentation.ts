export type BadgeTone = "neutral" | "success" | "warning" | "danger";

const intentLabels: Record<string, string> = {
  refund_request: "退款/售后申请",
  shipping_issue: "物流配送问题",
  invoice_request: "发票需求",
  account_issue: "账号/会员问题",
  complaint: "投诉升级",
  other: "其他咨询",
};

const intentDescriptions: Record<string, string> = {
  refund_request: "核对订单、政策和金额，给出退款审核建议。",
  shipping_issue: "查询订单配送状态，并引用物流延迟规则。",
  invoice_request: "识别开票诉求，必要时创建后续处理工单。",
  account_issue: "参考会员售后政策，判断是否需要人工协助。",
  complaint: "优先升级人工处理，保留处理记录。",
  other: "未命中标准售后场景，给出兜底回复或转人工建议。",
};

const categoryLabels: Record<string, string> = {
  refund: "退款售后",
  delivery: "物流配送",
  invoice: "发票服务",
  product_quality: "商品质量",
  exchange: "换货服务",
  account: "账号服务",
  complaint: "投诉升级",
  general: "通用咨询",
};

const statusLabels: Record<string, string> = {
  open: "待处理",
  pending: "处理中",
  escalated: "已转人工",
  resolved: "已解决",
  closed: "已关闭",
  success: "完成",
  skipped: "跳过",
  failed: "异常",
};

const priorityLabels: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
};

const feedbackTypeLabels: Record<string, string> = {
  accepted: "采纳",
  edited: "修改后采纳",
  rejected: "不采纳",
};

const policyStatusLabels: Record<string, string> = {
  draft: "草稿",
  published: "已发布",
  disabled: "已停用",
};

const toolLabels: Record<string, string> = {
  search_policy: "检索政策",
  get_order_info: "查询订单",
  check_refund_eligibility: "校验退款资格",
  calculate_refund_amount: "计算建议金额",
  create_ticket: "创建工单",
  update_ticket_status: "更新工单状态",
  escalate_to_human: "转人工处理",
};

const nodeLabels: Record<string, string> = {
  intent_classification: "识别问题类型",
  information_check: "核对关键信息",
  policy_retrieval: "匹配售后政策",
  tool_selection: "选择处理动作",
  business_action: "执行业务建议",
  response_generation: "生成客服回复",
  trace_recording: "记录处理过程",
};

const metricLabels: Record<string, string> = {
  intent_accuracy: "问题类型识别",
  tool_call_accuracy: "处理流程匹配",
  policy_hit_rate: "政策引用命中",
  human_escalation_accuracy: "人工升级判断",
  average_latency_ms: "平均响应耗时",
  auto_resolution_rate: "自动处理占比",
  p50_ms: "P50 响应耗时",
  p95_ms: "P95 响应耗时",
  max_ms: "最慢响应耗时",
  total_cases: "评测用例数",
  passed_cases: "通过用例数",
  failed_cases_count: "失败用例数",
};

const orderStatusLabels: Record<string, string> = {
  paid: "已支付",
  shipped: "已发货",
  delivered: "已签收",
  completed: "已完成",
  cancelled: "已取消",
  refunding: "退款处理中",
  refunded: "已退款",
};

const paymentStatusLabels: Record<string, string> = {
  unpaid: "未支付",
  paid: "已支付",
  refund_pending: "退款审核中",
  refunded: "已退款",
};

const refundReasonTranslations: Array<[RegExp, string | ((captured: string) => string)]> = [
  [
    /Order is paid and within a refundable status\./g,
    "订单已支付，且当前订单状态支持进入退款审核",
  ],
  [
    /Requested refund amount exceeds the order total\./g,
    "申请退款金额超过订单实付金额",
  ],
  [
    /Payment status is ([a-z_]+), not paid\./g,
    (status) => `当前支付状态为${labelPaymentStatus(status)}，不满足已支付要求`,
  ],
  [
    /Order status is already ([a-z_]+)\./g,
    (status) => `当前订单状态已是${labelOrderStatus(status)}，需要人工复核后再处理`,
  ],
];

export function labelIntent(intent: string): string {
  return intentLabels[intent] ?? intent;
}

export function describeIntent(intent: string): string {
  return intentDescriptions[intent] ?? "按客服规则进行处理。";
}

export function labelCategory(category: string): string {
  return categoryLabels[category] ?? category;
}

export function labelStatus(status: string): string {
  return statusLabels[status] ?? status;
}

export function statusTone(status: string): BadgeTone {
  if (status === "failed") {
    return "danger";
  }
  if (status === "escalated" || status === "skipped" || status === "pending") {
    return "warning";
  }
  if (status === "success" || status === "resolved" || status === "closed") {
    return "success";
  }
  return "neutral";
}

export function labelPriority(priority: string): string {
  return priorityLabels[priority] ?? priority;
}

export function labelFeedbackType(feedbackType: string): string {
  return feedbackTypeLabels[feedbackType] ?? feedbackType;
}

export function labelPolicyStatus(status: string): string {
  return policyStatusLabels[status] ?? status;
}

export function policyStatusTone(status: string): BadgeTone {
  if (status === "published") {
    return "success";
  }
  if (status === "disabled") {
    return "danger";
  }
  return "warning";
}

export function priorityTone(priority: string): BadgeTone {
  if (priority === "high") {
    return "danger";
  }
  if (priority === "medium") {
    return "warning";
  }
  return "neutral";
}

export function labelTool(toolName: string): string {
  return toolLabels[toolName] ?? toolName;
}

export function labelNode(node: string): string {
  return nodeLabels[node] ?? node;
}

export function labelMetric(metric: string): string {
  return metricLabels[metric] ?? metric;
}

export function labelOrderStatus(status: string): string {
  return orderStatusLabels[status] ?? status;
}

export function labelPaymentStatus(status: string): string {
  return paymentStatusLabels[status] ?? status;
}

export function localizeServiceReply(reply: string): string {
  const localized = refundReasonTranslations.reduce((current, [pattern, replacement]) => {
    if (typeof replacement === "string") {
      return current.replace(pattern, replacement);
    }
    return current.replace(pattern, (_matched, captured: string) =>
      replacement(captured),
    );
  }, reply);
  return localized.replace(/。{2,}/g, "。").replace(/；。/g, "。");
}

export function labelFailureReason(reason: string): string {
  const category = failureReasonCategory(reason);
  const labels: Record<string, string> = {
    policy_miss: "政策未命中",
    intent_mismatch: "问题类型识别错误",
    tool_mismatch: "处理流程不一致",
    human_escalation_mismatch: "人工升级判断错误",
    other: "其他质检问题",
  };
  return labels[category] ?? reason;
}

export function failureReasonCategory(reason: string): string {
  if (reason === "policy_miss" || reason.startsWith("policy miss")) {
    return "policy_miss";
  }
  if (reason === "intent_mismatch" || reason.startsWith("intent mismatch")) {
    return "intent_mismatch";
  }
  if (reason === "tool_mismatch" || reason.startsWith("tools mismatch")) {
    return "tool_mismatch";
  }
  if (
    reason === "human_escalation_mismatch" ||
    reason.startsWith("need_human mismatch")
  ) {
    return "human_escalation_mismatch";
  }
  return "other";
}

export function formatToolList(toolNames: string[]): string {
  return toolNames.length ? toolNames.map(labelTool).join("、") : "-";
}

export function policyScenario(title: string, sourceFile = ""): string {
  const text = `${title} ${sourceFile}`;
  if (text.includes("七天") || text.includes("特殊商品")) {
    return "退换货审核";
  }
  if (text.includes("物流")) {
    return "配送异常处理";
  }
  if (text.includes("发票")) {
    return "开票与补票";
  }
  if (text.includes("会员")) {
    return "会员售后权益";
  }
  if (text.includes("投诉") || text.includes("升级")) {
    return "投诉升级处理";
  }
  if (text.includes("退款")) {
    return "退款到账咨询";
  }
  return "通用售后咨询";
}

export function intentSortValue(intent: string): number {
  const order = [
    "refund_request",
    "shipping_issue",
    "invoice_request",
    "complaint",
    "account_issue",
    "other",
  ];
  const index = order.indexOf(intent);
  return index === -1 ? order.length : index;
}
