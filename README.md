# LLM Gateway

基于 FastAPI / PostgreSQL / Redis 的 LLM Gateway，提供统一 `/v1/chat/completions` 接口、网关 API Key 鉴权、Redis 限流、多上游路由、基础熔断，以及面向充值制售卖场景的余额计费。

## 项目结构

```text
llm-gateway/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── redis_client.py
│   ├── deps.py
│   ├── core/
│   ├── models/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   └── utils/
├── alembic/
│   ├── env.py
│   └── versions/
├── scripts/
│   └── seed_data.py
├── tests/
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 核心能力

- `POST /v1/chat/completions`：OpenAI 风格请求代理。
- `GET /v1/me/balance`：客户查询当前余额。
- `GET /v1/me/dashboard`：客户自助仪表盘数据，包含余额、请求、token、账本、模型消耗。
- `GET /health`：检查 API、PostgreSQL、Redis 健康状态。
- `GET /portal`：内置 Web 门户，支持用户名 + 专属 key 登录、充值、查看用量和网页调试。
- `GET /admin/providers`：列出当前 provider 及健康状态，仅 admin key 可访问。
- `POST /admin/providers`：添加 OpenAI / Anthropic / Mock provider。
- `POST /admin/pricing`：配置某个 provider 下某个模型的单价。
- `POST /admin/customers`：创建客户并签发网关 key。
- `POST /admin/topups`：给客户充值，支持“付款金额 / 毛利 / 实际授信额度”拆分。
- `GET /admin/usage/users`：按客户查看请求数、tokens、估算成本、实扣金额、剩余余额。
- `GET /admin/usage/models`：按 provider + model 查看汇总用量。
- `GET /admin/ledger/{user_id}`：查看某个客户的充值 / 扣费账本。
- 网关 API Key 只保存 HMAC-SHA256 hash，不存明文。
- 区分 `admin key` 与普通客户 key。
- 用户余额按 `Decimal` 记账，充值金额保留 2 位小数。
- 真实 usage 成本保留 6 位小数，避免模型计费精度损失。
- 可配置余额耗尽后自动禁用客户 key，充值后自动恢复。
- Redis 限流：
  - API Key 每分钟 60 次
  - IP 每分钟 120 次
- Provider 路由：
  - 根据 `model + priority + health` 选路
  - 失败时自动回退到下一个可用 provider
- Provider adapter：
  - `openai`：官方 / 兼容 OpenAI Chat Completions
  - `anthropic`：官方 Claude Messages API，自动映射到统一输出格式
  - `mock`：本地联调用
- 熔断：
  - 连续失败 3 次进入 60 秒冷却
  - 冷却期间不参与路由

## 环境变量

主要配置见 `.env.example`：

- `DATABASE_URL`：应用异步连接串
- `DATABASE_SYNC_URL`：Alembic 迁移连接串
- `REDIS_URL`：Redis 连接串
- `GATEWAY_API_KEY_HASH_SECRET`：网关 API Key 哈希密钥
- `ENABLE_MOCK_PROVIDER`：是否启用内置 mock provider
- `SEED_ADMIN_API_KEY`：初始化写入的 admin key
- `SEED_GATEWAY_API_KEY`：初始化脚本写入的测试网关密钥
- `SEED_DEMO_PAYMENT_AMOUNT`：演示客户付款金额
- `SEED_DEMO_MARGIN_AMOUNT`：演示客户毛利金额
- `AUTO_DISABLE_API_KEYS_ON_ZERO_BALANCE`：余额耗尽后是否自动禁用客户 key
- `SEED_PROVIDER_*`：可选真实上游 provider 初始化参数

## 本地启动

1. 创建虚拟环境并安装依赖：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 复制环境变量：

```bash
cp .env.example .env
```

3. 启动 PostgreSQL 和 Redis。

4. 执行迁移：

```bash
alembic upgrade head
```

5. 初始化测试数据：

```bash
python -m scripts.seed_data
```

6. 启动服务：

```bash
uvicorn app.main:app --reload
```

7. 打开门户：

```text
http://localhost:8000/portal
```

## Docker 启动

直接启动：

```bash
docker compose up --build
```

`app` 容器会自动执行：

```bash
alembic upgrade head
python -m scripts.seed_data
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 初始化测试数据

默认初始化内容：

- 管理员：`admin-user`
- 演示客户：`demo-user`
- Admin API Key：读取 `SEED_ADMIN_API_KEY`
- Customer API Key：读取 `SEED_GATEWAY_API_KEY`
- 演示客户余额：`SEED_DEMO_PAYMENT_AMOUNT - SEED_DEMO_MARGIN_AMOUNT`
- Mock provider：`local-mock-provider`

默认测试 key：

```text
gw_admin_local_key
gw_demo_local_key
```

如果你配置了下面这些环境变量，脚本还会额外插入一个真实 provider：

- `SEED_PROVIDER_BASE_URL`
- `SEED_PROVIDER_API_KEY`
- `SEED_PROVIDER_SUPPORTED_MODELS`

## 调用示例

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

### 2. Mock provider 直连

```bash
curl -X POST http://localhost:8000/mock/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "hello mock"}]
  }'
```

### 3. 通过网关请求 chat completions

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_demo_local_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Say hello from the gateway"}
    ],
    "temperature": 0.2,
    "max_tokens": 128
  }'
```

### 4. 查看当前余额

```bash
curl http://localhost:8000/v1/me/balance \
  -H "Authorization: Bearer gw_demo_local_key"
```

### 5. 查看 provider 列表

```bash
curl http://localhost:8000/admin/providers \
  -H "Authorization: Bearer gw_admin_local_key"
```

### 5.1 打开 Web 门户

浏览器访问：

```text
http://localhost:8000/portal
```

可直接粘贴：

- 演示用户：用户名 `demo-user`，key `gw_demo_local_key`
- 管理员：用户名 `admin-user`，key `gw_admin_local_key`

门户当前支持：

- 用“用户名 + API key”登录，而不是只粘贴 key
- 查看当前余额、累计请求、累计 token、累计扣费
- 查看最近请求和最近账本
- 在网页里直接发起一条测试 `/v1/chat/completions`
- 使用 admin key 创建新客户并签发唯一 gateway key
- 使用 admin key 给现有客户充值

### 6. 新增真实 OpenAI provider

```bash
curl -X POST http://localhost:8000/admin/providers \
  -H "Authorization: Bearer gw_admin_local_key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "openai-main",
    "provider_type": "openai",
    "base_url": "https://api.openai.com",
    "api_key": "sk-xxx",
    "supported_models": ["gpt-4o-mini"],
    "priority": 90,
    "weight": 100,
    "timeout_seconds": 30
  }'
```

### 7. 为 provider 配置价格

```bash
curl -X POST http://localhost:8000/admin/pricing \
  -H "Authorization: Bearer gw_admin_local_key" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": "replace-with-provider-id",
    "model_name": "gpt-4o-mini",
    "input_cost_per_1k_tokens": "0.12",
    "output_cost_per_1k_tokens": "0.24",
    "currency": "CNY"
  }'
```

### 8. 查看客户用量汇总

```bash
curl http://localhost:8000/admin/usage/users \
  -H "Authorization: Bearer gw_admin_local_key"
```

### 9. 查看模型用量汇总

```bash
curl http://localhost:8000/admin/usage/models \
  -H "Authorization: Bearer gw_admin_local_key"
```

### 10. 查看客户账本

```bash
curl http://localhost:8000/admin/ledger/<user_id> \
  -H "Authorization: Bearer gw_admin_local_key"
```

## 测试

```bash
pytest
```

当前最小测试覆盖：

- `/health`
- `/v1/chat/completions` 未鉴权返回 401
- `/v1/me/balance` 与余额扣减
- 限流触发时返回 429
- 非 admin key 访问 `/admin/providers` 返回 403
- admin 用量汇总与账本接口
- 余额清零自动禁用 key，充值后自动恢复

## 已知限制

- 当前只实现非流式请求，`stream=true` 会返回 `400`
- 价格表需要你手工录入或通过后台接口维护，目前不做自动汇率与官方价格同步
- 管理端目前只做了轻量写接口，还没有删除、编辑历史和多角色后台
- 限流为固定窗口实现，优先保证简单稳定

## 后续扩展建议

- SSE / chunked streaming
- 更精细的 provider 权重调度
- Prometheus 指标与告警
- 后台管理界面
- 更精确的模型成本配置与聚合报表
