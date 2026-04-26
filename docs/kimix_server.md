### 新建文件（`src/kimix/server/` 目录）

| 文件 | 说明 |
|------|------|
| `__init__.py` | 包初始化 |
| `bus.py` | **事件总线** — `EventBus` 单例，支持同步/异步订阅者，负责将 session 状态变化、消息更新等事件广播到所有 SSE 客户端 |
| `session_manager.py` | **Session 管理器** — 封装 `kimi_agent_sdk.Session`，提供 CRUD + prompt + abort，同时发射 opencode 兼容的事件（`message.part.updated`, `session.idle`, `session.status` 等） |
| `app.py` | **FastAPI 应用** — opencode-style REST API 路由，完整兼容 opencode 的 API 格式 |
| `serve.py` | **CLI 入口** — `kimix serve --host --port` 的处理函数，使用 uvicorn 启动 |
| `client.py` | **HTTP/SSE 客户端** — 包含 `KimixAsyncClient`（异步）和 `KimixSyncClient`（同步），以及 SSE 事件解析器 `parse_event()`，完全兼容 opencode SSE 协议 |

### API 路由对照表

| opencode 路由 | kimix serve 路由 | 状态 |
|---------------|------------------|------|
| `GET /global/health` | `GET /global/health` | ✅ |
| `GET /event` (SSE) | `GET /event` (SSE) | ✅ |
| `POST /session` | `POST /session` | ✅ |
| `GET /session` | `GET /session` | ✅ |
| `GET /session/status` | `GET /session/status` | ✅ |
| `GET /session/:id` | `GET /session/{id}` | ✅ |
| `DELETE /session/:id` | `DELETE /session/{id}` | ✅ |
| `PATCH /session/:id` | `PATCH /session/{id}` | ✅ |
| `GET /session/:id/message` | `GET /session/{id}/message` | ✅ |
| `POST /session/:id/message` | `POST /session/{id}/message` | ✅ |
| `POST /session/:id/prompt_async` | `POST /session/{id}/prompt_async` | ✅ |
| `POST /session/:id/abort` | `POST /session/{id}/abort` | ✅ |

### 修改的文件

1. **`src/kimix/cli_impl/core.py`** — 新增 `kimix serve` 子命令检测，优先于旧的 `--server` 模式
2. **`pyproject.toml`** — 新增依赖：`fastapi`, `uvicorn`, `sse-starlette`, `httpx`, `pydantic`
3. **`kimix_lark_bot/kimix_lark_bot/process_manager.py`** — 启动命令从 `kimix --server --port X --ws-port Y` 改为 `kimix serve --port X`
4. **`kimix_lark_bot/kimix_lark_bot/handlers.py`** — `TaskHandler` 从使用 `KimixSessionClient`（JSON-RPC）改为 `KimixSyncClient`（HTTP REST），使用 `health_check()`, `create_session()`, `send_message()` 等 opencode-style API

### 使用方式

```bash
# 启动 kimix serve（opencode-style HTTP server）
kimix serve --host 127.0.0.1 --port 4096

# 客户端使用（Python）
from kimix.server.client import KimixAsyncClient, KimixSyncClient, parse_event, EventType

# 同步
client = KimixSyncClient(port=4096)
sess = client.create_session("My Task")
msg = client.send_message(sess.id, "帮我写测试")

# 异步 + SSE
async with KimixAsyncClient(port=4096) as client:
    sess = await client.create_session("My Task")
    await client.send_prompt_async(sess.id, "帮我写测试")
    async for event in client.stream_events_robust(sess.id):
        parsed = parse_event(event, sess.id)
        if parsed.type == EventType.TEXT:
            print(parsed.delta, end="", flush=True)
        if parsed.is_terminal():
            break
```

旧的 `kimix --server`（JSON-RPC）仍然可用，作为 legacy 模式保留。
