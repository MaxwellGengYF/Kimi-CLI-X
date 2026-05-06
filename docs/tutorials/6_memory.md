# 记忆系统（Memory System）

记忆系统为 Agent 提供持久化与分层的信息管理能力，让 Agent 能够存储关键事实、检索历史上下文，并在长期交互中保持连贯性。

---

## 核心设计：三层记忆架构

| 层级 | 名称 | 特点 | 对应工具行为 |
| :--- | :--- | :--- | :--- |
| **L1** | 工作记忆（Working） | 临时缓存，用于当前会话的即时上下文 | `long_term=False` 时写入 |
| **L2** | 短期记忆（Short-term） | 近期感知，自动衰减 | `long_term=False` 时写入 |
| **L3** | 长期记忆（Long-term） | 重要知识持久化，支持语义检索与标签过滤 | `long_term=True`（默认）时写入 |

记忆条目包含重要性（`importance`）、时间衰减、访问次数加权，并支持按 `tags` 分类与过期时间（`expires_at`）控制。

---

## 记忆类型（MemoryType）

- **`semantic`**（默认）：语义知识、事实、概念。
- **`episodic`**：事件、经历、具体场景。
- **`working`**：工作上下文、临时状态。

---

## 可用工具

### 1. Remember —— 存储记忆

将事实、观察或知识存入记忆系统。

**关键参数：**

| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `content` | `str` | **必填** | 要存储的内容 |
| `importance` | `float` | `5.0` | 重要性评分 `0-10`，越高越不容易被遗忘 |
| `tags` | `list[str]` | `[]` | 分类标签，用于后续过滤检索 |
| `memory_type` | `MemoryType` | `SEMANTIC` | 记忆类型：`semantic` / `episodic` / `working` |
| `long_term` | `bool` | `True` | `True` 存入 L3 长期记忆；`False` 存入 L1+L2 |
| `expires_at` | `float \| None` | `None` | 绝对过期时间戳，到期后条目失效 |

**使用建议：**
- 关键知识、用户偏好、项目规范 → `long_term=True`，适当提高 `importance`。
- 临时上下文、单次会话的中间结果 → `long_term=False`。

---

### 2. Recall —— 检索记忆

从全部或指定层级中检索与查询相关的记忆。

**关键参数：**

| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `query` | `str` | **必填** | 检索关键词/语义查询 |
| `context_size` | `int` | `5` | 每层返回的最大条数 `1-20` |
| `use_working` | `bool` | `True` | 是否包含工作记忆（L1） |
| `use_short` | `bool` | `True` | 是否包含短期记忆（L2） |
| `use_long` | `bool` | `True` | 是否包含长期记忆（L3） |
| `tags` | `list[str]` | `[]` | 仅过滤长期记忆中包含指定标签的条目 |

**使用建议：**
- 回答用户问题前先 `Recall`，获取历史相关上下文。
- 通过 `tags` 快速定位特定领域记忆（如 `["project", "api"]`）。

---

### 3. Reflect —— 记忆状态与反思

查看记忆系统状态，可选执行深度自我反思。

| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `deep` | `bool` | `False` | `True` 执行深度自我反思；`False` 仅返回状态报告 |

---

## 典型调用流程

```
1. 遇到新信息 / 用户输入
   └─> Remember(content="...", importance=7, tags=["user_pref"])

2. 需要回答或执行任务
   ├─> Recall(query="...", tags=["user_pref"])

3. 定期维护
   └─> Reflect(deep=True) 检查记忆健康度
```

---

## 最佳实践

1. **重要性分级**：核心业务逻辑、用户明确要求的规则设 `importance >= 7`；临时日志、中间推导可设 `3-5`。
2. **标签规范**：为同一项目/模块使用统一标签（如 `{"project:foo", "api", "bugfix"}`），便于精准过滤。
3. **过期控制**：敏感或时效性信息（如临时 token、待办事项）设置 `expires_at`，避免长期污染记忆。
4. **检索优先**：生成回复前优先调用 `Recall` 或 `GetContext`，而非直接依赖模型预训练知识。
5. **层级选择**：当前会话的临时变量用 `long_term=False`（L1/L2），跨会话必须保留的信息才进 L3。
