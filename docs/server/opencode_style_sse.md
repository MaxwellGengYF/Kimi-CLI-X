# OpenCode SSE 协议分析

## 1. 整体交互流程

```
┌─────────┐                          ┌───────────────┐
│  Client  │                          │ OpenCode HTTP │
└────┬─────┘                          └──────┬────────┘
     │  1. GET /global/health                │
     │ ─────────────────────────────────────→ │  200 OK
     │                                       │
     │  2. POST /session                     │
     │ ─────────────────────────────────────→ │  200 OK (Session JSON)
     │                                       │
     │  3. POST /session/{id}/prompt_async   │
     │ ─────────────────────────────────────→ │  204 No Content (fire-and-forget)
     │                                       │
     │  4. GET /event (SSE stream)           │
     │ ─────────────────────────────────────→ │  200 OK (text/event-stream)
     │                                       │
     │  ← server.connected                   │
     │  ← session.diff                       │
     │  ← session.status (busy)              │
     │  ← message.part.updated (step-start)  │
     │  ← message.part.updated (reasoning)   │ ×N (增量推送)
     │  ← message.part.updated (tool/pending)│
     │  ← message.part.updated (tool/running)│
     │  ← message.part.updated (tool/completed)│
     │  ← message.part.updated (step-finish, reason=tool-calls)│
     │  ← ... (新一轮 step) ...              │
     │  ← message.part.updated (text)        │ ×N (增量推送)
     │  ← message.part.updated (step-finish, reason=stop) │ ← 终止信号
     │                                       │
```

### 关键设计点

| 特性 | 说明 |
|------|------|
| Prompt 异步发送 | `POST /session/{id}/prompt_async` 返回 **204 No Content**，不等待结果 |
| SSE 全局端点 | `/event` 推送**所有 session** 的事件，客户端需按 `sessionID` 过滤 |
| SSE 传输格式 | `Transfer-Encoding: chunked`，`Connection: keep-alive` |
| 无 SSE `event:` 字段 | 所有事件的 SSE `event` 字段为空，类型信息在 JSON `data.type` 中 |

## 2. HTTP API 端点

### 2.1 健康检查

```
GET /global/health
→ 200 {"healthy": true, ...}
```

### 2.2 Session 管理

```
POST   /session                          → 200 Session JSON
GET    /session/{id}                     → 200 Session JSON
DELETE /session/{id}                     → 200
GET    /session                          → 200 [Session, ...]
GET    /session/{id}/message?limit=N     → 200 [Message, ...]
GET    /session/status                   → 200 Status JSON
POST   /session/{id}/abort              → 200
POST   /session/{id}/permissions/{pid}   → 200
```

### 2.3 Prompt 发送

```
POST /session/{id}/prompt_async
Body: {"parts": [{"type": "text", "text": "..."}], "agent"?: "...", "model"?: "..."}
→ 204 No Content
```

### 2.4 SSE 事件流

```
GET /event
→ 200 text/event-stream
   Cache-Control: no-cache
   Connection: keep-alive
   Transfer-Encoding: chunked
```

## 3. SSE 事件类型详解

### 3.1 事件格式

所有 SSE 事件使用统一的 JSON `data` 字段，**没有使用 SSE 的 `event:` 字段**：

```
data: {"type":"<event_type>","properties":{...}}

```

注意：每条事件后跟一个空行（SSE 标准分隔符）。

### 3.2 事件分类总览

| SSE `data.type` | 作用 | 重要性 |
|---|---|---|
| `server.connected` | SSE 连接建立确认 | 🔇 可忽略 |
| `session.status` | 会话状态变更 (`busy` / `idle`) | ⚡ `idle` 时为终止信号 |
| `session.diff` | 文件变更差异 | 🔇 可忽略 |
| `session.updated` | 会话元信息更新 | 🔇 可忽略 |
| `message.updated` | 消息级别元信息更新 | 🔇 可忽略 |
| **`message.part.updated`** | **核心事件：消息部件更新** | ⭐ **核心** |

### 3.3 `message.part.updated` — 核心事件

这是最重要的事件类型，通过内部 `properties.part.type` 字段进一步区分子类型。

#### 3.3.1 `step-start` — 推理步骤开始

```json
{
  "type": "message.part.updated",
  "properties": {
    "part": {
      "id": "prt_...",
      "sessionID": "ses_...",
      "messageID": "msg_...",
      "type": "step-start",
      "snapshot": "cfefd5eb..."
    }
  }
}
```

- 标志新一轮推理步骤的开始
- 一次完整回复中可能有**多个 step**（reasoning → tool → reasoning → text → stop）

#### 3.3.2 `reasoning` — 模型推理过程

```json
{
  "type": "message.part.updated",
  "properties": {
    "part": {
      "id": "prt_...",
      "sessionID": "ses_...",
      "messageID": "msg_...",
      "type": "reasoning",
      "text": "The user wants to know what files are in the current directory and their main content. Let me check.",
      "time": {"start": 1777272244147}
    },
    "delta": " to know what files are in the current"
  }
}
```

| 字段 | 说明 |
|------|------|
| `part.text` | **累积全文**（每次事件都包含从开头到当前的全部文本） |
| `delta` | **增量文本**（本次新增的片段） |
| `part.time.start` | 推理开始时间戳（毫秒） |
| `part.time.end` | 推理结束时间戳（仅在最后一条 reasoning 事件中出现） |

**增量推送模式**：reasoning 事件会逐 token 推送，每条事件同时携带 `text`（全文快照）和 `delta`（增量）。

#### 3.3.3 `tool` — 工具调用

工具调用有三个阶段，通过 `state.status` 区分：

**① pending（待执行）**
```json
{
  "type": "message.part.updated",
  "properties": {
    "part": {
      "id": "prt_...",
      "type": "tool",
      "callID": "toolu_bdrk_01AHraxAfLa1vYxfXd93ey64",
      "tool": "read",
      "state": {"status": "pending", "input": {}, "raw": ""}
    }
  }
}
```

**② running（执行中）**
```json
{
  "properties": {
    "part": {
      "type": "tool",
      "callID": "toolu_bdrk_...",
      "tool": "read",
      "state": {
        "status": "running",
        "input": {"filePath": "F:\\repos\\ai\\cube-claw\\dashboard\\src\\hooks"},
        "time": {"start": 1777272244874}
      }
    }
  }
}
```

**③ completed（执行完成）**
```json
{
  "properties": {
    "part": {
      "type": "tool",
      "callID": "toolu_bdrk_...",
      "tool": "read",
      "state": {
        "status": "completed",
        "input": {"filePath": "F:\\repos\\...\\hooks"},
        "output": "<path>...</path>\n<type>directory</type>\n<entries>..."
      }
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `callID` | 工具调用的唯一 ID（可用于匹配 pending → running → completed） |
| `tool` | 工具名称，如 `read`、`write`、`bash` 等 |
| `state.status` | 生命周期：`pending` → `running` → `completed` / `error` |
| `state.input` | 工具输入参数（running 阶段出现） |
| `state.output` | 工具输出结果（completed 阶段出现） |
| `state.time.start` | 工具执行开始时间戳 |

#### 3.3.4 `text` — 文本回复

```json
{
  "type": "message.part.updated",
  "properties": {
    "part": {
      "id": "prt_...",
      "type": "text",
      "text": "只有一个文件 **`use-mobile.tsx`**：",
      "time": {"start": 1777272257447}
    },
    "delta": "有一个文件 "
  }
}
```

- 与 reasoning 相同的增量推送模式：`text` = 全文快照，`delta` = 增量
- 最后一条 text 事件会带 `time.end` 字段
- 这是 LLM 给用户的**最终可见回复**

#### 3.3.5 `step-finish` — 推理步骤结束

```json
{
  "type": "message.part.updated",
  "properties": {
    "part": {
      "id": "prt_...",
      "type": "step-finish",
      "reason": "tool-calls",
      "snapshot": "cfefd5eb...",
      "cost": 2.313666,
      "prompt": {"total": 29551},
      "tokens": {
        "input": 3,
        "output": 115,
        "reasoning": 0,
        "cache": {"read": 0, "write": 25360}
      }
    }
  }
}
```

| 字段 | 说明 |
|------|------|
| `reason` | **`tool-calls`** = 步骤结束但还有后续步骤（工具执行后继续）；**`stop`** = 完全结束 |
| `cost` | 本步骤的 API 费用 |
| `tokens` | 本步骤的 token 用量明细 |
| `tokens.cache` | 缓存命中情况（`read` = 缓存读取，`write` = 写入缓存） |

### 3.4 终止信号判定

客户端通过以下逻辑判断 SSE 流是否应该结束：

```python
def is_terminal(self) -> bool:
    if self.type == EventType.SESSION_IDLE:
        return True
    if self.type == EventType.STEP_FINISH:
        return self.text not in ("tool-calls", "tool_calls")
    return False
```

即：
1. **`session.status` 中 `status.type == "idle"`** → 终止
2. **`step-finish` 中 `reason != "tool-calls"`**（如 `reason == "stop"`）→ 终止

## 4. 完整会话事件流时序

以日志中的实际交互为例，用户提问后的完整事件流：

```
14:43:59  → POST /session/{id}/prompt_async (204)
14:43:59  → GET /event (SSE 连接建立)

=== 连接建立阶段 ===
14:43:59  ← server.connected                    [SKIP]
14:43:59  ← session.diff                        [SKIP]
14:43:59  ← session.status (busy)               [SKIP]

=== Step 1: 推理 + 工具调用 ===
14:44:04  ← step-start                          ← 新步骤开始
14:44:04  ← reasoning (delta × 6)               ← "The user wants to know..."
14:44:04  ← tool/read (pending)                 ← 工具排队
14:44:04  ← tool/read (running)                 ← 开始读取目录
14:44:04  ← reasoning (time.end)                ← reasoning 结束快照
14:44:04  ← tool/read (completed)               ← 读取完成
14:44:05  ← step-finish (reason=tool-calls)     ← 步骤结束，还有下一步

=== 步间事件 ===
14:44:05  ← message.updated (×2)                [SKIP]
14:44:05  ← session.status (busy)               [SKIP]
14:44:05  ← message.updated                     [SKIP] (新 message 创建)
14:44:05  ← session.updated                     [SKIP]

=== Step 2: 继续工具调用 ===
14:44:11  ← step-start
14:44:11  ← tool/read (pending → running → completed) ← 读取文件
14:44:12  ← step-finish (reason=tool-calls)

=== 步间事件 ===
14:44:12  ← message.updated (×3)                [SKIP]
14:44:12  ← session.updated, session.diff        [SKIP]

=== Step 3: 生成最终回复 ===
14:44:17  ← step-start
14:44:17  ← text (delta × ~30)                  ← "只有一个文件 `use-mobile.tsx`..."
14:44:18  ← text (time.end)                     ← 文本输出完成
14:44:19  ← step-finish (reason=stop)           ← ★ 终止信号
```

## 5. 多步推理模式 (Agentic Loop)

OpenCode 的一个核心特征是**多步推理循环（Agentic Loop）**：

```
Step 1: reasoning → tool-call(s) → step-finish(tool-calls)
                                          ↓
        [服务端执行工具，注入结果到上下文]
                                          ↓
Step 2: tool-call(s) → step-finish(tool-calls)
                                          ↓
Step 3: reasoning → text(回复) → step-finish(stop)  ← 结束
```

每次 `step-finish(reason=tool-calls)` 表示「我还需要更多工具调用结果」，服务端会自动发起下一轮推理。客户端只需持续监听 SSE 流直到收到终止信号。

## 6. ID 命名规范

| 前缀 | 对象 | 示例 |
|------|------|------|
| `ses_` | Session | `ses_2325232b2ffe0XLh4YnYAOAiZF` |
| `msg_` | Message | `msg_dcdae34e30014kj6BZM7pwb1ct` |
| `prt_` | Part | `prt_dcdae47b2001AnTvk0IB378E5A` |
| `toolu_bdrk_` | Tool Call | `toolu_bdrk_01AHraxAfLa1vYxfXd93ey64` |

## 7. 客户端实现要点

### 7.1 必须处理的事件

| 优先级 | 事件 | 处理方式 |
|--------|------|----------|
| P0 | `text` (delta) | 逐增量输出给用户 |
| P0 | `step-finish` (reason=stop) | 终止 SSE 监听 |
| P1 | `tool` (running/completed/error) | 展示工具执行状态 |
| P1 | `reasoning` (delta) | 可选展示思考过程 |
| P2 | `step-start` | UI 分隔符 |
| P2 | `session.status` (idle) | 备用终止信号 |

### 7.2 可安全忽略的事件

- `server.connected`、`server.heartbeat`
- `message.updated`、`message.created`
- `session.updated`、`session.created`、`session.diff`
- `session.status` (非 idle)

### 7.3 重连机制

- SSE 连接可能因网络原因断开
- 客户端应实现自动重连（建议最多 5 次，间隔递增）
- 重连后 `/event` 会重新推送 `server.connected`

### 7.4 会话过滤

`/event` 是**全局端点**，会推送所有 session 的事件。客户端必须通过以下字段过滤：

```
properties.sessionID
properties.part.sessionID
properties.info.sessionID
```

## 8. `message.updated` 中的元信息（参考）

虽然 `message.updated` 通常被忽略，但它包含有价值的元信息：

```json
{
  "type": "message.updated",
  "properties": {
    "info": {
      "id": "msg_...",
      "sessionID": "ses_...",
      "role": "assistant",
      "time": {"created": 1777272239331, "completed": 1777272245667},
      "parentID": "msg_...",
      "modelID": "claude-opus-4-6",
      "providerID": "netease-codemaker",
      "mode": "Sisyphus - Ultraworker",
      "agent": "Sisyphus - Ultraworker",
      "path": {
        "cwd": "F:\\repos\\ai\\cube-claw\\dashboard\\src\\hooks",
        "root": "F:\\repos\\ai\\cube-claw"
      },
      "cost": 2.313666,
      "tokens": {"input": 3, "output": 115, "reasoning": 0}
    }
  }
}
```

可用于：追踪费用、确认模型/Agent 信息、消息完成时间等。
