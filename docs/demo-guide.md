# 演示指南

这份文档用于本地启动和面试演示。当前项目默认运行在 Windows + VSCode + PowerShell 环境。

## 启动顺序

### 1. 启动 PostgreSQL 和 Qdrant

```powershell
cd E:\code3\kefuAgent
docker compose up -d postgres qdrant
```

确认容器配置：

```powershell
docker compose config
```

### 2. 启动后端

```powershell
cd E:\code3\kefuAgent\backend

$env:DATABASE_URL = 'postgresql+psycopg://postgres:123456@localhost:5432/postgres'
$env:QDRANT_URL = 'http://localhost:6333'
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
$env:AGENT_MODE = 'rules'

# 可选智能增强：需要阿里云 DashScope API Key；失败会回退 rules
# $env:AGENT_MODE = 'llm_assisted'
# $env:DASHSCOPE_API_KEY = '<your-api-key>'
# $env:DASHSCOPE_MODEL = 'qwen-plus'

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### 3. 首次初始化数据

如果数据库或 Qdrant 是空的，另开一个 PowerShell 终端运行：

```powershell
cd E:\code3\kefuAgent\backend

$env:DATABASE_URL = 'postgresql+psycopg://postgres:123456@localhost:5432/postgres'
$env:QDRANT_URL = 'http://localhost:6333'
$env:KEFU_EMBEDDING_BACKEND = 'hashing'

.\.venv\Scripts\python.exe -m scripts.init_db
.\.venv\Scripts\python.exe -m scripts.seed_db
.\.venv\Scripts\python.exe -m scripts.ingest_knowledge
```

### 4. 启动前端

```powershell
cd E:\code3\kefuAgent\frontend
npm run dev
```

默认访问：

```text
http://localhost:5173
```

## 推荐演示路径

### 场景 1：退款审核

页面：客服处理台

输入：

```text
ORD-2026-0002 商品坏了我要退款
```

演示点：

- 系统识别为退款/售后申请。
- 系统展示可自动回复或建议转人工。
- 系统引用七天无理由、退款到账、特殊商品等政策。
- 处理结论只给退款审核建议，不真实退款。
- 前端面向客服展示中文业务文案，不暴露工具名和原始 JSON。

### 场景 2：物流异常

输入：

```text
订单 ORD-2026-0001 的物流一直没更新
```

演示点：

- 系统识别为物流配送问题。
- 查询订单和物流记录。
- 检索物流延迟赔付规则。
- 给出客服可读的回复草稿。

### 场景 3：投诉升级

输入：

```text
我要投诉，ORD-2026-0031 的售后处理太慢了
```

演示点：

- 系统识别为投诉升级。
- 高风险场景建议人工处理。
- 可以创建或升级工单。

### 场景 4：质检中心

页面：质检中心

演示点：

- 当前 50 条评测用例全部通过。
- 可以按场景查看退款、物流、发票、投诉、账号、其他的质量。
- 展示平均耗时、P95 响应耗时和历史趋势。

### 场景 5：智能增强开关

页面：客服处理台

演示点：

- 打开“智能增强”后，刷新页面仍保持打开。
- 关闭后同样持久化保持关闭。
- 有阿里云 DashScope API Key 时，系统可辅助理解非标准表达并润色回复。
- 无 API Key 或调用失败时，系统仍使用稳定规则处理。
- 页面只展示业务文案，不展示模型、API Key、工具名或 JSON。

## 验证命令

前端：

```powershell
cd E:\code3\kefuAgent\frontend
npm run build
```

后端：

```powershell
cd E:\code3\kefuAgent\backend

$env:DATABASE_URL = 'postgresql+psycopg://postgres:123456@localhost:5432/postgres'
$env:QDRANT_URL = 'http://localhost:6333'
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
$env:AGENT_MODE = 'rules'

.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
```

评测：

```powershell
cd E:\code3\kefuAgent\backend

$env:DATABASE_URL = 'postgresql+psycopg://postgres:123456@localhost:5432/postgres'
$env:QDRANT_URL = 'http://localhost:6333'
$env:KEFU_EMBEDDING_BACKEND = 'hashing'

.\.venv\Scripts\python.exe -m scripts.run_eval --mode rules
```

## 常见问题

### 8000 端口被占用

```powershell
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### 5432 或 6333 端口被占用

先确认是否已有项目容器在运行。不要重复 `docker compose up` 导致端口冲突。

### Qdrant 没有数据

重新导入知识库：

```powershell
cd E:\code3\kefuAgent\backend
$env:QDRANT_URL = 'http://localhost:6333'
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
.\.venv\Scripts\python.exe -m scripts.ingest_knowledge
```

### fastembed 首次加载慢

本地演示优先使用：

```powershell
$env:KEFU_EMBEDDING_BACKEND = 'hashing'
```

### 递归搜索 backend 报 Access is denied

不要直接递归扫整个 `backend`，会扫进 `.venv`、pytest 临时缓存或 cache 目录。优先限定：

```powershell
Get-ChildItem -Path backend\app,backend\tests,backend\scripts -Recurse -File
```

### 评测写报告遇到 PermissionError

受限沙箱可能无法写 `data/eval/eval_report.json`。在本机 VSCode 终端正常运行即可。
