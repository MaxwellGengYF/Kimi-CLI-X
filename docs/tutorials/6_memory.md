# 记忆系统（Memory System）

记忆系统为 Agent 提供持久化与分层的信息管理能力，让 Agent 能够存储关键事实、检索历史上下文，并在长期交互中保持连贯性。

本文档内容整理自 `src/kimix/memory/` 下的核心实现文件：`system.py`、`types.py`、`working_memory.py`、`short_term_memory.py`、`long_term_memory.py`、`sqlite_backend.py`、`embedding.py`、`tools.py`。

---

## 核心设计：三层记忆架构

| 层级 | 名称 | 容量 / 生命周期 | 写入方式 | 检索方式 |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | 工作记忆（Working） | 固定容量 10 条，超出自动丢弃最旧条目 | `Remember(long_term=False)` 时自动写入，或 `perceive()` 调用 | 直接返回最近的 `n` 条 |
| **L2** | 短期记忆（Short-term） | 容量 100 条，TTL 3600s，超出按有效重要性淘汰 | `Remember(long_term=False)` 时自动写入，或 `perceive()` 调用 | 语义相似度搜索 + 字符串相似度回退 |
| **L3** | 长期记忆（Long-term） | 持久化存储（SQLite 或 JSON），无硬性容量限制 | `Remember(long_term=True)`（默认）时写入；每 100 次交互后，高重要性短期记忆自动迁移（consolidation） | 混合语义 + BM25 + 字符串相似度 + LTR 重排序 + 多样性重排 |

**`Remember` 与 `perceive` 的区别：**

- **`long_term=True`（默认）**：调用 `system.remember()`，内容以 `SEMANTIC` 类型直接进入 **L3 长期记忆**。
- **`long_term=False`**：调用 `system.perceive()`，内容以 `EPISODIC` 类型同时进入 **L1 工作记忆** 和 **L2 短期记忆**。

---

## 记忆条目（MemoryEntry）

每条记忆包含以下字段：

| 字段 | 说明 |
| :--- | :--- |
| `content` | 记忆文本内容 |
| `memory_type` | `semantic` / `episodic` / `working` |
| `timestamp` | 创建时间戳 |
| `importance` | 基础重要性（1.0–10.0） |
| `access_count` | 被访问次数 |
| `last_accessed` | 最后访问时间戳 |
| `embedding` | 384 维向量（由 EmbeddingProvider 生成） |
| `tags` | 分类标签列表 |
| `source` | 来源标识（如 `environment`、`agent_learning`） |
| `expires_at` | 可选的绝对过期时间戳 |
| `agent_id` | 所属 agent ID |

### 有效重要性计算

系统使用动态的有效重要性（`effective_importance`）来决定淘汰和排序：

```
effective_importance = importance × recency × (1.0 + access_boost)
```

- **`recency`**：基于时间的指数衰减，半衰期约为 7 天。`recency = exp(-0.1 × Δdays)`
- **`access_boost`**：访问次数加成，每次访问 +0.1，上限 2.0（即最多 ×3）

---

## EmbeddingProvider：确定性特征哈希

长期记忆和短期记忆的语义检索不依赖外部神经网络模型，而是使用内置的 **EmbeddingProvider** 生成 384 维确定性向量：

1. **特征哈希**：将文本分词后，对 unigram 和 bigram 使用 MD5 哈希到 384 维向量中（带符号），并附加前缀、后缀、长度、词数、数字/标点统计等特征。
2. **归一化**：输出向量为单位长度（L2 norm = 1）。
3. **缓存**：内置 LRU 缓存（默认 4096 条），避免重复计算。

这意味着记忆系统的嵌入计算**无需 GPU、无需下载模型**，完全本地离线运行。

---

## L3 长期记忆检索 pipeline

长期记忆的 `retrieve()` 是一个多阶段混合检索 pipeline，远超简单的向量相似度搜索：

1. **查询预处理**
   - 拼写纠正（NoisyChannelSpeller，基于索引内词频）
   - Porter Stemming 词干提取

2. **候选召回**
   - 若指定 `tag_filter`，先按标签交集过滤
   - 否则遍历所有未过期且重要性达标的条目

3. **多路打分**
   - **语义相似度**：预归一化向量的点积 × 有效重要性
   - **BM25**：自适应权重（根据查询性能预测器 QPP 动态调整 0.1–0.7）
   - **字符串相似度**：Jaro-Winkler + Sørensen-Dice + N-gram overlap 的平均值

4. **查询扩展**
   - RM3 伪相关反馈扩展
   - Rocchio 扩展

5. **LTR 重排序**
   - 使用 LambdaMART / RankSVM / RankBoost 对 Top-K 结果重新排序

6. **多样性重排**
   - 优先使用 xQuAD（基于标签 aspect）
   - 回退到 MMR（Maximal Marginal Relevance）

7. **访问更新**
   - 返回结果自动更新 `access_count` 和 `last_accessed`

### 近重复检测（Near-Deduplication）

写入长期记忆时，系统会自动检测近重复内容：
- **SimHash LSH**：捕获语义近重复和完全重复
- **I-Match 指纹**：精确指纹回退

若发现重复，新内容不会独立存储，而是**提升原有条目的重要性**（`existing.importance += new.importance × 0.5`）并合并标签。

---

## 数据持久化

### SQLiteBackend（默认）

默认情况下，长期记忆使用 SQLite 存储（`.kimix_cache/memory.db`）：

- **WAL 模式**：支持高并发读写
- **连接池**：1 个写入连接 + 3 个读取连接池
- **索引**：按 `memory_type`、`timestamp`、`expires_at`、`agent_id` 组合索引
- **标签表**：独立的 `memory_tags` 表，支持多对多关系
- **批量操作**：`store_many`、`update_access_many` 均针对大批量做了 chunked 优化
- **自动维护**：`Reflect(deep=True)` 每 100 次交互会自动执行 `VACUUM` + `ANALYZE`

### JSON 文件回退

当 `use_sqlite=False` 时，长期记忆退化为 JSON 文件存储（`.kimix_cache/ltm.json`），此时近重复检测、BM25 索引均在内存中维护。

---

## Consolidation（记忆固化）

每 **100 次交互**（`perceive` 调用），系统会自动执行 consolidation：

1. 扫描短期记忆缓冲区中的所有条目
2. 筛选出 **有效重要性 ≥ 6.0** 且未过期的条目
3. 将这些条目迁移到长期记忆
4. 从短期记忆中移除已迁移的条目
5. 清理短期记忆中的过期条目

这意味着**高价值短期记忆会自动升级为长期记忆**，无需手动干预。

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
| `long_term` | `bool` | `True` | `True` 存入 L3；`False` 存入 L1+L2 |
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
| `use_agent` | `bool` | `False` | 启用子 agent 对检索结果进行深度分析 |

**使用建议：**
- 回答用户问题前先 `Recall`，获取历史相关上下文。
- 通过 `tags` 快速定位特定领域记忆（如 `["project", "api"]`）。

---

### 3. Reflect —— 记忆状态与反思

查看记忆系统状态，可选执行深度自我反思。

| 参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `deep` | `bool` | `False` | `True` 执行深度自我反思；`False` 仅返回状态报告 |

**深度反思（`deep=True`）会执行以下操作：**
- 扫描长期记忆中低访问（<2 次）且陈旧（>7 天）的条目，降低其重要性
- 提升高频访问（≥5 次）条目的重要性
- 清理短期记忆中的过期条目
- 若使用 SQLite 后端且交互次数达到 100 的倍数，自动执行数据库优化（`VACUUM` + `ANALYZE`）

---

### 4. Forget —— 遗忘记忆

降低或删除长期记忆中的某条记录。

**工作机制：**
- 根据内容哈希定位目标条目
- 将其重要性乘以 `0.5`
- 若重要性降至 `< 0.1`，则**彻底删除**该条目
- 若未低于阈值，则保留但降低权重

**使用建议：**
- 用于清理过时、错误或不再相关的长期记忆
- 临时记忆（L1/L2）无需手动遗忘，它们会自动 TTL 淘汰

---

## 典型调用流程

```
1. 遇到新信息 / 用户输入
   └─> Remember(content="...", importance=7, tags=["user_pref"])

2. 需要回答或执行任务
   ├─> Recall(query="...", tags=["user_pref"])
   └─> 系统自动从 L1/L2/L3 合并返回相关上下文

3. 定期维护（每 100 次交互自动触发）
   └─> Consolidation：高价值短期记忆 → 长期记忆

4. 手动深度维护
   └─> Reflect(deep=True) 检查记忆健康度并优化数据库
```

---

## 最佳实践

1. **重要性分级**：核心业务逻辑、用户明确要求的规则设 `importance >= 7`；临时日志、中间推导可设 `3-5`。
2. **标签规范**：为同一项目/模块使用统一标签（如 `["project:foo", "api", "bugfix"]`），便于精准过滤。
3. **过期控制**：敏感或时效性信息（如临时 token、待办事项）设置 `expires_at`，避免长期污染记忆。
4. **检索优先**：生成回复前优先调用 `Recall`，让系统从三层记忆中检索上下文，而非仅依赖模型预训练知识。
5. **层级选择**：当前会话的临时变量用 `long_term=False`（L1/L2），跨会话必须保留的信息才进 L3。
6. **定期 Reflect**：在长时间运行后手动调用 `Reflect(deep=True)`，清理低质量记忆并优化 SQLite 性能。
7. **利用自动 Consolidation**：高重要性短期记忆会自动升级为长期记忆，无需手动重复 `Remember`。
