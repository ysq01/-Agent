# 系统架构说明

本项目是一个电商售后客服工单自动处理 Agent。当前版本采用规则状态机保证主流程可控，并提供可选的阿里云 DashScope LLM-assisted 智能增强。系统通过真实 PostgreSQL、Qdrant RAG、业务工具 API、React 工作台和评测系统构成完整闭环。

## 架构目标

- 让客服能够输入用户问题，并得到可执行的处理建议。
- 让 Agent 基于真实订单、物流、工单和政策知识库做判断。
- 让退款等高风险动作只停留在审核建议层，不直接修改支付和库存。
- 让评测系统持续验证意图识别、工具调用、政策命中和人工升级判断。

## 主要模块

### 前端工作台

位置：`frontend/src`

- `App.tsx`：客服处理台、工单中心、政策知识库、质检中心。
- `api.ts`：封装后端 HTTP 请求。
- `types.ts`：前端请求和响应类型。
- `presentation.ts`：把内部字段映射为中文业务文案。
- `styles.css`：企业后台风格页面样式。

前端默认面向中国客服用户，不展示 API 路径、数据库字段、工具名、原始 JSON 或开发者诊断信息。
客服处理台提供“智能增强”开关，开关状态保存在浏览器本地。开关只决定是否允许后端尝试 LLM 辅助理解和润色，不授权任何高风险业务动作。

### FastAPI 后端

位置：`backend/app/api`

- `agent.py`：`POST /api/agent/process`
- `tools.py`：业务工具 API
- `tickets.py`：工单只读 API
- `knowledge.py`：知识库文档 API
- `evaluation.py`：评测报告 API

### 数据层

位置：`backend/app/models`

当前模型：

- `User`：用户基础信息、会员等级。
- `Product`：商品 SKU、分类、价格、库存状态。
- `Order`：订单号、订单状态、支付状态、总金额。
- `OrderItem`：订单明细。
- `Shipment`：物流记录。
- `Ticket`：客服工单。

初始化方式使用 `Base.metadata.create_all`，暂未引入 Alembic。

### 业务工具服务

位置：`backend/app/services/tools.py`

工具包括：

- 查询订单
- 查询用户
- 查询物流
- 检查退款资格
- 计算退款金额建议
- 创建工单
- 更新工单状态
- 升级人工

退款工具只返回审核建议，不真实退款，不改支付状态，不改库存。

### 政策知识库 RAG

位置：

- `data/knowledge`
- `backend/app/services/policy_knowledge.py`
- `backend/scripts/ingest_knowledge.py`

当前政策文档：

- 七天无理由退货规则
- 特殊商品退货规则
- 物流延迟赔付规则
- 发票规则
- 会员售后权益
- 投诉升级规则
- 退款到账时间说明

本地开发可设置：

```powershell
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
```

这样可以避免 fastembed 首次下载或加载模型带来的不稳定。

### Agent 工作流

位置：`backend/app/services/agent_workflow.py`

当前使用规则状态机作为主流程，不使用 LangGraph。可选 `llm_assisted` 模式只插入在意图辅助理解和回复润色两个窄接口中。

节点：

```text
intent_classification
information_check
policy_retrieval
tool_selection
business_action
response_generation
trace_recording
```

LLM-assisted 模式的数据流：

```text
规则意图识别
  -> 低置信度或 other 时可选 LLM 辅助识别
  -> 规则信息检查、政策检索、工具选择和业务动作
  -> 规则生成回复
  -> 可选 LLM 润色回复
  -> 安全文案和高风险动作校验
```

支持意图：

- `refund_request`
- `shipping_issue`
- `invoice_request`
- `account_issue`
- `complaint`
- `other`

### 评测系统

位置：

- `data/eval/customer_service_eval_cases.jsonl`
- `backend/app/services/evaluation.py`
- `backend/scripts/run_eval.py`
- `frontend/src/App.tsx` 的质检中心

评测覆盖：

- refund 12
- shipping 8
- invoice 7
- complaint 8
- account 5
- other 10

指标：

- 问题类型识别
- 处理流程匹配
- 政策命中
- 人工升级判断
- 自动处理占比
- 平均耗时、P50、P95、最大耗时

当前最新结果：50 total，50 passed，0 failed。

## 核心数据流

```text
客服输入用户问题
  -> 前端调用 POST /api/agent/process
  -> Agent 识别问题类型
  -> 检查必要信息
  -> 检索政策知识库
  -> 按意图选择业务工具
  -> 查询 PostgreSQL 或 Qdrant
  -> 生成处理建议和客服回复
  -> 前端展示问题类型、处理结论、参考政策和工单信息
```

## 安全边界

- 退款只做资格检查和审核建议。
- 不真实调用支付退款。
- 不修改支付状态。
- 不修改库存。
- 投诉和账号类问题默认倾向人工处理。
- 评测脚本默认事务 rollback，避免污染演示数据。

## 下一阶段架构方向

第 11 阶段增加可选 `LLM-assisted` 模式：

```text
rules mode:
  规则状态机完成全部处理

llm_assisted mode:
  阿里云 DashScope LLM 辅助理解用户表达和润色回复
  规则状态机仍负责流程控制
  业务工具仍负责事实查询和高风险校验
```

这个方向能展示大模型能力，同时保留业务系统的确定性和安全边界。没有 `DASHSCOPE_API_KEY` 或模型调用失败时，系统会回退到 rules 输出。
