# LLM Gateway

自用 LLM API 中转网关。基于 FastAPI + React，提供统一的 OpenAI 兼容接口，支持多 Provider 路由、按 Token 计费、余额管理和 Stripe 支付。

## 项目结构

```text
llm-gateway/
├── app/                    # FastAPI 后端
│   ├── main.py
│   ├── config.py
│   ├── deps.py             # 鉴权依赖
│   ├── models/             # SQLAlchemy 模型
│   ├── routers/            # API 路由
│   ├── schemas/            # Pydantic 模型
│   ├── services/           # 业务逻辑
│   └── utils/
├── frontend/               # React + TypeScript 前端
│   ├── src/
│   │   ├── api/client.ts   # Axios 封装
│   │   ├── context/        # AuthContext
│   │   ├── components/     # Layout 等
│   │   └── pages/          # Dashboard, ApiKeys, Usage, TopUp, Login, Register
│   ├── package.json
│   └── vite.config.ts
├── alembic/                # 数据库迁移
├── scripts/seed_data.py    # 初始化测试数据
├── tests/
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## 核心功能

### API 代理
- `POST /v1/chat/completions` — OpenAI 兼容接口，支持流式和非流式
- 基于 LangGraph 状态机的 Provider 路由，自动 Fallback
- 支持 OpenAI、Anthropic、Gemini 三种 Provider 类型
- 连续失败 3 次自动熔断，60 秒冷却

### 用户系统
- JWT + API Key 双重鉴权
- 邮箱密码注册/登录
- 自助管理 API Key（创建/吊销）

### 计费系统
- 充值制，Decimal 全链路精度
- 按实际 Token 用量扣费（input/output 独立定价）
- 余额归零自动禁用 Key，充值后自动恢复
- Stripe 支付集成（Webhook 幂等处理）

### 管理后台
- Provider 管理（增/查）
- 模型定价配置（支持通配符 `*`）
- 客户管理、充值、账本查询
- 按用户/模型维度用量报表

### 限流
- API Key 维度：60 次/分钟
- IP 维度：120 次/分钟

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- PostgreSQL 16+
- Redis 7+

### 后端启动

```bash
# 1. 安装依赖
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的配置

# 3. 启动数据库和 Redis（或用 docker compose）
docker compose up postgres redis -d

# 4. 迁移数据库
alembic upgrade head

# 5. 初始化测试数据
python -m scripts.seed_data

# 6. 启动服务
uvicorn app.main:app --reload
```

### 前端启动

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

### Docker 一键启动（仅后端）

```bash
docker compose up --build
```

### 前端环境变量

```bash
cd frontend
cp .env.example .env
# 编辑 VITE_API_BASE_URL 指向你的后端地址
```

## 环境变量说明

所有配置见 `.env.example`，关键项：

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | PostgreSQL 异步连接串 |
| `REDIS_URL` | Redis 连接串 |
| `GATEWAY_API_KEY_HASH_SECRET` | API Key 哈希密钥（生产必改） |
| `JWT_SECRET` | JWT 签名密钥（生产必改） |
| `CORS_ORIGINS` | 允许的前端域名，逗号分隔 |
| `STRIPE_SECRET_KEY` | Stripe 密钥（可选） |
| `STRIPE_WEBHOOK_SECRET` | Stripe Webhook 签名密钥（可选） |
| `SEED_PROVIDER_*` | 初始化真实 Provider 的配置（可选） |

## 调用示例

```bash
# 健康检查
curl http://localhost:8000/health

# Chat Completions（用你的 API Key 替换）
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Hello"}]
  }'

# 查询余额
curl http://localhost:8000/v1/me/balance \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## 测试

```bash
pytest
```

## 技术栈

**后端**: FastAPI, SQLAlchemy 2.0, LangChain, LangGraph, PostgreSQL, Redis, Stripe

**前端**: React 18, TypeScript, Vite, Tailwind CSS, Axios
