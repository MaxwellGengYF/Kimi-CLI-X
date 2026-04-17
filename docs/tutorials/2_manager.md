# Kimix Manager 深度解析与使用指南

`kimix_manager` 是 Kimix 框架的**任务编排与调度中枢**。它通过模拟「公司-设计师-程序员」的组织协作模式，将用户的原始需求自动拆解为可执行的任务单元（Job），再分发到多个 Worker 上并发执行，并在完成后进行验证。本文将从源码层面深入剖析其三大核心模块，并给出完整的使用示例。

---

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户交互层 (company.py)                      │
│  create_company()  schedule_project()  start_work()  designer()     │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      任务调度层 (designer.py)                        │
│         Designer 类：负责需求分析 (_work_designer)                   │
│                    负责代码执行 (_work_programmer)                 │
│                    负责入口路由 (work)                              │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        基础运行时 (base.py)                          │
│   Job 类：任务数据模型                                               │
│   Worker 类：任务存储、提取、执行                                    │
│   全局 Worker 队列：环形调度、并发执行                               │
└─────────────────────────────────────────────────────────────────────┘
```

核心设计理念：

1. **分层解耦**：`company.py` 暴露简单 API，`designer.py` 处理复杂 LLM 交互，`base.py` 管理底层并发与持久化。
2. **人机协作**：`Designer` 既能让 LLM 自动规划（Designer 分支），也能直接执行已定义好的任务（Programmer 分支）。
3. **并发弹性**：Worker 以环形队列（ring-queue）方式被调度，多个 Worker 可在 `ThreadPoolExecutor` 中并行消费任务。

---

## 二、基础运行时：base.py

`base.py` 是整个 Manager 的地基，包含数据模型 `Job`、执行单元 `Worker` 以及全局队列管理。

### 2.1 Job —— 任务数据模型

`Job` 类定义了一个任务的标准 JSON 结构：

```json
{
  "steps": ["step1", "step2"],
  "target": "way to validate",
  "directory": "relative/path",
  "skills": ["skill1", "skill2"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `steps` | `list[str]` | 是 | 按顺序执行的提示词步骤 |
| `target` | `str` | 否 | 验收标准，用于 Programmer 分支最后的验证环节 |
| `directory` | `str` | 否 | 任务的工作目录（相对路径） |
| `skills` | `list[str]` | 否 | 执行该任务时需要加载的 skill 名称列表 |

**序列化与反序列化**：

- `job.serialize()` → 生成 JSON 字符串，并做类型校验。
- `Job.deserialize(data)` → 从 JSON 字符串解析，调用 `check_json_dict_validate` 做严格校验（包括 skill 是否存在于 skill 目录中、directory 是否为合法 Windows 路径等）。

### 2.2 Worker —— 任务执行单元

每个 `Worker` 实例维护一个轻量级本地「数据库」：

- **存储位置**：`{name}.db/.worker.json`
- **数据结构**：字典 `job_name → job_path`
- **线程安全**：所有读写操作受 `threading.Lock` 保护

关键方法：

| 方法 | 作用 |
|------|------|
| `add_job(name, job)` | 若传入 `Job` 对象，先序列化保存为 `{name}.json`，再将路径写入 db；若传入字符串路径，则直接记录路径。 |
| `get_job(name)` | 从 db 中读取路径，反序列化为 `Job` 对象返回。 |
| `execute_jobs()` | **清空** db 中所有任务，为每个任务启动线程执行 `self._task(data)`，并 `join` 等待完成。返回执行的任务数。 |
| `has_jobs()` | 检查 db 是否非空。 |
| `clear_db()` | 清空内存 db 并删除持久化文件。 |

> **注意**：`execute_jobs()` 的设计是「一次性清空并执行」。这意味着同一个任务不会被重复执行，但也要求调用方在合适的时机触发执行。

### 2.3 全局 Worker 队列

```python
_workers: deque[Worker] = deque()
```

- `add_worker(worker)`：注册 Worker。
- `get_worker()`：**环形队列调度**（dequeue from left, enqueue to right），实现简单的轮询负载均衡。
- `get_all_workers()`：获取当前所有 Worker 的快照。
- `execute_all_jobs()`：最上层的并发调度器，逻辑如下：
  1. 为每个 Worker 在线程池中提交 `worker_loop`。
  2. `worker_loop` 反复调用 `worker.execute_jobs()`，直到该 Worker 无任务为止。
  3. 一轮执行完毕后，再次检查是否还有 Worker 产生了新任务（包括动态新增的 Worker），若有则继续循环，直到全局无任务。

这种设计允许任务在执行过程中动态生成新的子任务并被下一轮消费。

---

## 三、核心调度层：designer.py

`designer.py` 中的 `Designer` 类是整个 Manager 的**大脑**。它串联了 LLM 会话、需求分析和代码执行。

### 3.1 初始化

```python
Designer(folder: str, clear=False)
```

- 创建 `folder` 目录作为工作区。
- 在 `folder/worker.db` 下初始化一个 `Worker`，并将其注册到全局队列。
- `clear=True` 会清空 Worker 的历史 db。

### 3.2 双分支工作模式

`Designer.work(job_path)` 是整个类的总入口。它会智能判断输入内容的类型，决定走哪条分支：

| 输入类型 | 分支 | 说明 |
|----------|------|------|
| 文件路径，且内容是合法 `Job` JSON | Programmer | 直接执行 |
| 文件路径，但内容不是 Job JSON | Designer | 让 LLM 分析需求并生成 Job JSON |
| 非路径的字符串，且是合法 `Job` JSON | Programmer | 直接解析执行 |
| 非路径的字符串，也不是 JSON | Designer | 视为需求文件路径（若不存在会失败） |

### 3.3 Designer 分支：_work_designer

这是**架构师/设计师**的角色。流程如下：

1. **确定输出文件**：将需求文件名去掉扩展名，加上 `__task.json` 后缀，保存到 `folder` 下。例如 `req.md` → `req__task.json`。
2. **构建 Prompt**：向 LLM 发送指令，要求它：
   - 分析需求文件；
   - 将任务拆分为 `steps`；
   - 指定一个合理的 `directory`；
   - 编写 `target` 作为验收标准；
   - 从已有的 skill 目录中挑选合适的 `skills`。
3. **调用 LLM**：使用 `agent_boss.yaml` 配置的 agent（具备文件读写、搜索、Todo 管理等工具），最多重试 3 次。
4. **校验输出**：通过 `check_json()` 和 `Job.check_json_dict_validate()` 双重校验生成的 JSON。若失败，会将错误信息回传 LLM 要求修正。
5. **交互确认（ask_mode）**：若全局开启了 `ask_mode`（通过 `company.create_company` 设置），会询问用户是否立即将生成的 Job 提交给 Programmer。
6. **提交任务**：将生成的 JSON 文件作为任务，交给 `Worker` 执行。

### 3.4 Programmer 分支：_work_programmer

这是**程序员/执行者**的角色。流程如下：

1. **创建 LLM 会话**：使用默认的 `agent_worker.yaml` 配置（具备 `Python`、`Run`、`StrReplaceFile`、`Spawn` 等开发工具）。
2. **构建前缀**：
   - 若 `job.skills` 非空，则在每个 step 前加上 `use skill:xxx.` 的指令；
   - 若 `job.directory` 非空，则加上 `in dir \`xxx\`` 的上下文约束。
3. **顺序执行 steps**：逐个调用 `prompt(step, session=session)`，LLM 会自主调用工具完成编码、文件修改、测试运行等操作。
4. **关闭执行会话**：释放上下文，避免验证阶段与执行阶段的状态互相干扰。
5. **验证阶段（Validation）**：
   - 若 `job.target` 存在，开启新的验证会话，要求 LLM「编写一个全面的测试文件来验证该 target，并修复任何错误」。
   - 使用 `validate()` 工具函数进行判断。若首次验证未通过，还会 fallback 到更直接的提示词继续尝试最多 3 次。

---

## 四、用户交互层：company.py

`company.py` 是面向终端用户或上层脚本的最简 API。它屏蔽了 `Designer` 和 `Worker` 的创建细节。

### 4.1 核心 API

```python
create_company(designer_folder='designer', ask_mode=False, clear_db=False)
```

- 初始化全局的 `_designer` 实例。
- `ask_mode=True` 时，每次 LLM 生成 Job 后都会询问用户是否继续执行。
- `clear_db=True` 时，会清空 Worker 的历史任务记录。

```python
schedule_project(content: str, job_name: str = None)
```

- 将一段需求文本（`content`）写入临时 `.md` 文件。
- 从全局 Worker 队列中获取一个 Worker（轮询），将该临时文件作为任务提交。
- 若 `job_name` 为空，会自动生成 `job_0`、`job_1` 等名称。

```python
start_work()
```

- 调用 `execute_all_jobs()`，启动所有 Worker 的并发执行。
- 所有任务完成后，清空各 Worker 的 db。

```python
designer(content: str) -> Path | None
```

- 直接调用 `_designer._work_designer()`，**仅生成 Job JSON 文件并返回其路径**，不提交给 Programmer。适用于需要人工 review 任务规划的场景。

```python
worker(job: Job)
```

- 直接调用 `_designer._work_programmer()`，**绕过 Designer 分支**，立即执行一个已构造好的 `Job` 对象。适用于程序化任务下发。

---

## 五、完整工作流示例

以下示例展示了从最上层 API 到底层数据结构的完整使用方式。

### 5.1 方式一：全自动流程（推荐）

```python
from kimix_manager.company import create_company, schedule_project, start_work

# 1. 初始化公司
create_company(designer_folder='my_designer', ask_mode=False, clear_db=True)

# 2. 调度多个项目需求
schedule_project("""
请为项目创建一个 Python 模块 `calculator.py`，实现加、减、乘、除四个函数，
并编写对应的单元测试 `test_calculator.py`，确保所有测试通过。
工作目录设为 `math_tools`。
""", job_name="calculator_task")

schedule_project("""
请创建一个 `README.md`，介绍 `calculator.py` 的用法和安装方式。
工作目录设为 `math_tools`。
""", job_name="readme_task")

# 3. 开始执行
start_work()
```

执行过程：
1. `schedule_project` 将两个 `.md` 需求文件分别提交到 `my_designer/worker.db` 中。
2. `start_work` 触发 `execute_all_jobs()`。
3. Worker 取出任务，逐个调用 `Designer.work(file_path)`。
4. 由于 `.md` 不是 Job JSON，进入 **Designer 分支**，LLM 分析后生成对应的 `__task.json`。
5. 生成的 JSON 被重新作为任务提交给同一个 Worker。
6. 再次执行时，进入 **Programmer 分支**，LLM 真正开始写代码、运行测试。
7. 最后执行 `target` 验证，确保质量达标。

### 5.2 方式二：半自动流程（人工 review 任务规划）

```python
from kimix_manager.company import create_company, designer, worker, start_work
from kimix_manager.base import Job

create_company(designer_folder='my_designer')

# 仅生成任务规划 JSON，不执行
job_path = designer("请实现一个支持 JWT 认证的 FastAPI 用户登录接口。")
print(f"任务规划已保存至: {job_path}")

# 人工检查 job_path 内容后，再决定执行
# ...

# 读取并执行
with open(job_path, 'r', encoding='utf-8') as f:
    job = Job.deserialize(f.read())

worker(job)
```

### 5.3 方式三：直接构造 Job 对象（完全程序化）

```python
from kimix_manager.company import create_company, worker
from kimix_manager.base import Job

create_company()

job = Job()
job.steps = [
    "在 `src/utils.py` 中实现一个 `fibonacci(n)` 函数",
    "在 `tests/test_utils.py` 中编写 pytest 测试，覆盖 n=0,1,10",
    "运行 pytest 确保全部通过"
]
job.target = "pytest 运行后所有测试用例通过，且无语法错误"
job.directory = "src"
job.skills = ["tool"]  # 若存在 tool skill，可引导 LLM 使用

worker(job)
```

---

## 六、并发与调度细节

### 6.1 单 Worker 内部并发

`Worker.execute_jobs()` 在取出所有任务后，会为**每个任务启动一个独立线程**执行：

```python
thds: list[threading.Thread] = []
for data in jobs_data:
    thds.append(run_thread(lambda: self._task(data)))
for i in thds:
    i.join()
```

这意味着：一个 Worker 一次可以并行处理多个 Job，但任务是从 db 中一次性取空的，取完后再并发执行。执行完毕后才会返回。

### 6.2 多 Worker 之间并发

`execute_all_jobs()` 使用 `ThreadPoolExecutor` 为每个 Worker 分配一个线程，持续循环直到全局无任务：

```python
with ThreadPoolExecutor(max_workers=len(workers)) as executor:
    futures = {executor.submit(worker_loop, worker): i for i, worker in enumerate(workers)}
    for future in as_completed(futures):
        future.result()
```

### 6.3 Worker 的环形队列调度

```python
def get_worker() -> Worker | None:
    with _workers_mutex:
        if not _workers:
            return None
        worker = _workers.popleft()
        _workers.append(worker)
        return worker
```

当多次调用 `schedule_project()` 时，任务会被轮流分配到不同的 Worker 上，实现最简单的负载均衡。

---

## 七、数据持久化与状态管理

### 7.1 Worker DB

Worker 的 db 是一个简单的 JSON 文件，存储在 `{worker_name}.db/.worker.json` 中：

```json
{
  "calculator_task": "calculator_task.json",
  "readme_task": "readme_task.json"
}
```

- 支持进程/会话中断后的部分恢复（虽然当前实现是内存优先，异常时会回退到空状态）。
- `clear_db()` 会同时清理内存和磁盘文件。

### 7.2 Job JSON 文件

Designer 分支生成的 `__task.json` 会持久保存在 `designer_folder` 下，便于：
- 人工 review
- 版本控制
- 后续复用或修改后重新提交

---

## 八、错误处理与健壮性

### 8.1 JSON 生成容错

`_work_designer` 对 LLM 生成的 JSON 有**三重保障**：
1. `json.load()` 基础语法检查；
2. `Job.check_json_dict_validate()` 业务逻辑检查（字段类型、skill 存在性、路径合法性）；
3. 最多 3 次重试，每次将错误信息反馈给 LLM 修正。

### 8.2 路径安全

`check_path_format()` 函数对 `directory` 字段做了严格的 Windows 路径校验：
- 禁止字符：`<>"|?*`
- 禁止保留名：`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`
- 禁止尾部空格或句点

### 8.3 异常捕获

`execute_all_jobs`、`Worker.execute_jobs`、`_work_programmer` 等关键路径均有大范围的 `try/except` 保护，防止单个任务失败导致整个调度器崩溃。

---

## 九、进阶技巧

### 9.1 多 Worker 配置

虽然 `company.py` 目前只创建一个 Designer（含一个 Worker），但你可以绕过 `company.py`，直接使用 `base.py` 和 `designer.py` 的 API 注册多个 Worker：

```python
from kimix_manager.base import Worker, add_worker, execute_all_jobs
from kimix_manager.designer import Designer

d1 = Designer('designer_a', clear=True)
d2 = Designer('designer_b', clear=True)
# 每个 Designer 内部已自动 add_worker(...)

# 手动获取特定 worker 并添加任务
from kimix_manager.base import get_all_workers
workers = get_all_workers()
workers[0].add_job("task_a", job_a)
workers[1].add_job("task_b", job_b)

execute_all_jobs()
```

### 9.2 自定义 Agent 配置

`Designer` 的 `_work_designer` 使用 `agent_boss.yaml`，`_work_programmer` 使用默认的 `agent_worker.yaml`。如果你需要让任务规划阶段使用更强的模型，或让执行阶段开放更多/更少工具，可以：

1. 复制并修改 `src/kimix/agent_boss.yaml` 或 `agent_worker.yaml`；
2. 在调用 `create_session(agent_file='your_agent.yaml')` 时指定自定义配置。

### 9.3 与 CLI 结合

在 Kimix CLI 的交互环境中，你可以直接导入 `kimix_manager.company` 模块，利用 `/script` 命令运行上述 Python 脚本，实现批量任务的自动化调度。

---

## 十、总结

| 层级 | 文件 | 核心职责 | 典型用户 |
|------|------|----------|----------|
| 交互层 | `company.py` | 提供极简 API 初始化、调度、执行 | 终端用户、脚本编写者 |
| 调度层 | `designer.py` | LLM 需求分析、任务执行、结果验证 | 框架开发者 |
| 运行时 | `base.py` | Job 模型、Worker 单元、并发调度 | 框架开发者 |

`kimix_manager` 的设计精髓在于：**用 LLM 充当 Designer 进行任务分解，用结构化 JSON 作为中间产物，再让 LLM 充当 Programmer 执行并验证**。这种「规划-执行-验证」的闭环，使得复杂需求能够被可靠地自动化完成，同时保留了人类介入和 review 的灵活性。
