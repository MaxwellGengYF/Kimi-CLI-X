# HTTP 服务端 (FastAPI + SSE)

Kimix 提供兼容 OpenCode 协议的 **FastAPI + SSE** HTTP 服务端，通过 REST API 管理会话，使用 Server-Sent Events (SSE) 实时推送推理过程和工具调用状态。

> **协议参考**：完整的 SSE 事件类型、增量推送模式、终止信号判定等协议细节，请参阅 [`docs/server/opencode_style_sse.md`](../server/opencode_style_sse.md)。

---

## 一、快速启动

### 1. 安装依赖

```bash
pip install uvicorn
```

### 2. 启动服务

```bash
uv run kimix serve --host 127.0.0.1 --port 4096
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `127.0.0.1` | 绑定主机地址 |
| `--port` | `4096` | 绑定端口 |

启动后：

```
kimix server listening on http://127.0.0.1:4096
API docs (Swagger UI): http://127.0.0.1:4096/docs
OpenAPI schema: http://127.0.0.1:4096/openapi.json
Press Ctrl+C to stop
```

---

## 二、API 端点

所有端点兼容 OpenCode 标准。

### 2.1 健康检查

```
GET /global/health
→ 200 {"healthy": true, "version": "0.1.0"}
```

### 2.2 Session 管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/session` | 创建新会话（Body: `{"title": "..."}`） |
| `GET` | `/session` | 列出所有活跃会话 |
| `GET` | `/session/{sessionID}` | 获取会话元信息 |
| `DELETE` | `/session/{sessionID}` | 删除会话 |
| `GET` | `/session/status` | 获取所有会话状态（`idle`/`busy`/`error`） |

**创建会话示例：**

```bash
curl -X POST http://127.0.0.1:4096/session \
  -H "Content-Type: application/json" \
  -d '{"title": "My Session"}'
```

响应：

```json
{
  "id": "ses_xxxxxxxxxxxx",
  "title": "My Session",
  "createdAt": 1716883200.0,
  "updatedAt": 1716883200.0,
  "parentID": null
}
```

### 2.3 消息发送

```
POST /session/{sessionID}/prompt_async
Body: {"parts": [{"type": "text", "text": "你的提示词"}], "agent": "..." (可选), "model": "..." (可选)}
→ 204 No Content
```

这是一个 **fire-and-forget** 端点——发送后立即返回 204，不等待 LLM 结果。推理过程通过 SSE `/event` 流式推送。

**发送消息示例：**

```bash
curl -X POST http://127.0.0.1:4096/session/ses_xxx/prompt_async \
  -H "Content-Type: application/json" \
  -d '{"parts": [{"type": "text", "text": "请帮我写一个 Hello World 脚本"}]}'
```

**内置斜杠命令**：`prompt_async` 支持以下特殊命令前缀：

| 命令 | 说明 |
|------|------|
| `/clear` | 清空当前会话 |
| `/compact` | 压缩对话上下文 |
| `/context` | 获取上下文使用情况 |
| `/export` | 导出会话消息 |

### 2.4 消息查询

```
GET /session/{sessionID}/message?limit=N
→ 200 [Message, ...]
```

### 2.5 会话控制

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/session/{sessionID}/abort` | 中止当前正在执行的 prompt |
| `POST` | `/session/{sessionID}/permissions/{permissionID}` | 授予待处理的权限请求 |
| `GET` | `/session/{sessionID}/clear` | 清空会话 |
| `GET` | `/session/{sessionID}/context` | 获取会话上下文信息 |
| `GET` | `/session/{sessionID}/compact?keep=N` | 压缩会话历史（`keep` 默认 10） |
| `GET` | `/session/{sessionID}/export?output_path=PATH` | 导出会话消息到文件 |

---

## 三、SSE 事件流

### 3.1 全局事件端点

```
GET /event
→ 200 text/event-stream
```

`/event` 是**全局端点**，推送所有 session 的事件。客户端必须按 `sessionID` 过滤。

### 3.2 事件格式

所有事件使用纯 `data:` 行，**不使用 SSE `event:` 字段**（兼容 OpenCode 标准）：

```
data: {"type":"<event_type>","properties":{...}}

```

### 3.3 核心事件类型

| 事件类型 | 说明 | 重要性 |
|----------|------|--------|
| `server.connected` | SSE 连接建立确认 | 可忽略 |
| `session.status` | 会话状态 (`busy` / `idle`) | `idle` 为终止信号 |
| `session.diff` | 文件变更差异 | 可忽略 |
| `session.updated` | 会话元信息更新 | 可忽略 |
| `message.updated` | 消息级元信息 | 可忽略 |
| `message.part.updated` | **核心：消息部件更新** | ⭐ 必须处理 |

### 3.4 `message.part.updated` 子类型

| `part.type` | 说明 |
|-------------|------|
| `step-start` | 新一轮推理步骤开始 |
| `reasoning` | 模型思考过程（增量推送：`text` = 全文，`delta` = 增量） |
| `tool` | 工具调用（`pending` → `running` → `completed`/`error`） |
| `text` | LLM 最终文本回复（增量推送） |
| `step-finish` | 步骤结束。`reason=tool-calls` 表示还有后续步骤，`reason=stop` 表示完全结束 |

### 3.5 终止信号

客户端通过以下任一条件判定流结束：

1. `session.status` 中 `status.type == "idle"`
2. `step-finish` 中 `reason != "tool-calls"`（如 `reason == "stop"`）

### 3.6 完整交互时序

```
POST /session/{id}/prompt_async → 204 (fire-and-forget)
GET /event                       → SSE stream 建立

← server.connected               [连接确认]
← session.status (busy)          [开始处理]
← message.part.updated (step-start)
← message.part.updated (reasoning) ×N  [思考过程，增量推送]
← message.part.updated (tool/pending)   [工具排队]
← message.part.updated (tool/running)   [工具执行中]
← message.part.updated (tool/completed) [工具完成]
← message.part.updated (step-finish, reason=tool-calls) [还有后续]
← ... (新一轮 step) ...
← message.part.updated (text) ×N       [最终回复，增量推送]
← message.part.updated (step-finish, reason=stop)  [★ 终止]
```

---

## 四、SSE CLI 调试器 (`ssecli`)

Kimix 内置了一个 SSE 客户端调试工具，用于连接 `kimix serve` 进行交互式测试：

```bash
uv run kimix ssecli --host 127.0.0.1 --port 4096 --debug
```

| 参数 | 说明 |
|------|------|
| `--host` | 服务端地址（默认 `127.0.0.1`） |
| `--port` | 服务端端口（默认 `4096`） |
| `--debug` | 打印 SSE 原始事件并保存到日志文件 `sse_log_<timestamp>.txt` |

### 内置命令

| 命令 | 说明 |
|------|------|
| `/new` | 创建新会话 |
| `/abort` | 中止当前 prompt |
| `/status` | 查看所有会话状态 |
| `/sessions` | 列出所有会话 |
| `/messages` | 查看当前会话消息 |
| `/clear` | 清空当前会话 |
| `/compact` | 压缩上下文 |
| `/export` | 导出会话 |
| `/help` | 帮助信息 |

按 `Ctrl+C` 或输入 EOF（`Ctrl+D` / `Ctrl+Z`）退出。

---

## 五、Dummy 模式（测试用）

`src/kimix/server/dummy_app.py` 提供完整的桩服务端，所有端点返回 stub 响应，无需真实 LLM 后端。适用于前端开发、集成测试。

与真实服务端的区别：

- `dummy_app.py` 使用 `DummySessionManager`（无实际逻辑）
- SSE `/event` 仅推送 `server.connected` + heartbeat
- `prompt_async` 仅打印请求参数，不执行推理

运行方式：

```python
import uvicorn
from kimix.server.dummy_app import create_app

uvicorn.run(create_app(), host="127.0.0.1", port=4096)
```

---

## 六、客户端实现要点

### 6.1 必须处理的事件

| 优先级 | 事件 | 处理 |
|--------|------|------|
| P0 | `text` (delta) | 增量输出给用户 |
| P0 | `step-finish` (reason=stop) | 终止 SSE 监听 |
| P1 | `tool` (running/completed/error) | 展示工具执行状态 |
| P1 | `reasoning` (delta) | 可选展示思考过程 |

### 6.2 会话过滤

`/event` 是全局端点，客户端须按 `sessionID` 过滤：

```
properties.sessionID
properties.part.sessionID
properties.info.sessionID
```

### 6.3 重连机制

- SSE 连接断开时实现自动重连（建议最多 5 次，递增间隔）
- 重连后 `/event` 会重新推送 `server.connected`

---

## 七、架构概览

```
┌──────────┐  REST API   ┌─────────────┐     ┌──────────────────┐
│  Client   │ ◄─────────► │  FastAPI App │────►│ SessionManager   │
│ (curl /   │  POST/GET   │  (app.py)    │     │ (create/delete/  │
│  Web UI)  │             │              │     │  prompt_async)   │
└──────────┘             └──────┬───────┘     └──────────────────┘
                                │
                           SSE  │  /event
                                │
                         ┌──────▼───────┐
                         │   Bus (队列)  │
                         │  广播事件到    │
                         │  所有 SSE 客户端│
                         └──────────────┘
```

- **`app.py`**：FastAPI 应用工厂，定义所有路由和 SSE 流
- **`session_manager.py`**：会话生命周期管理（创建、删除、prompt 执行）
- **`bus.py`**：事件总线，广播 SSE 事件到所有连接的客户端
- **`dummy_app.py`** / **`dummy_session_manager.py`**：桩实现，用于测试
- **`serve.py`**：`kimix serve` CLI 入口，启动 uvicorn
