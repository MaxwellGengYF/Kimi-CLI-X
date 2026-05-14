# Kimix 快速入门指南

本文档将带你完成 Kimix 的环境准备、安装以及 CLI 的基本使用。

---

## 一、快速安装

如果你只想快速体验 Kimix，可直接通过 pip 安装：

```bash
# 安装
pip install kimix
# 运行
python -m kimix.cli
# 或
python -m kimix
```

如需从源码进行更深入的定制或开发，请参考下方的详细步骤。

---

## 二、Git Submodule 的拉取

Kimix 项目依赖部分通过 Git Submodule 管理。在首次获取代码后，需要确保所有子模块都已正确拉取。

### 1. 克隆时一并拉取

如果你在克隆仓库时已经使用了 `--recursive` 参数，submodule 会随主仓库一起下载，无需额外操作：

```bash
git clone --recursive <仓库地址>
```

### 2. 已克隆仓库后补拉或更新

如果你已经克隆了仓库但忘记添加 `--recursive`，或者需要更新已有的 submodule，可采用以下任一方式：

#### 方式 A：使用项目提供的脚本（推荐）

Kimix 提供了 `clone_submodule.py` 脚本，可一键完成 submodule 的拉取：

```bash
uv run clone_submodule.py
```

该脚本会自动处理 submodule 的初始化与递归更新，适合不想手动输入 Git 命令的用户。

#### 方式 B：手动执行 Git 命令

在仓库根目录执行以下命令：

```bash
git submodule update --init --recursive
```

该命令会完成两件事：

- `--init`：初始化本地配置文件，将 submodule 注册到 `.git/config` 中；
- `--recursive`：递归地拉取并更新所有嵌套的子模块到对应提交的版本。

执行完毕后，项目依赖的第三方库、工具脚本或其他资源即会完整就绪。

---

## 三、使用 uv 安装与运行

推荐使用 [uv](https://docs.astral.sh/uv/) 进行 Python 包管理和环境隔离。以下是 Kimix 的标准安装流程：

### 1. 进入项目根目录

项目根目录即包含 `pyproject.toml` 的目录：

```bash
cd /path/to/kimix
```

### 2. 可编辑模式安装并注册快捷命令

```bash
uv tool install -e .
```

说明：

- `-e .` 表示将当前目录以**可编辑方式**安装，代码修改无需重新安装即可生效；
- `uv tool install` 会将 `kimix` 命令注册到 uv 的工具路径中，使其在终端可直接调用。

### 3. 在任意目录运行 Kimix

```bash
uv run kimix
```

说明：

- `uv run kimix` 会自动使用 uv 管理的 Python 环境运行 `kimix`；
- 无需手动激活虚拟环境，也无需担心当前工作目录下的依赖冲突。

---

## 四、环境变量配置

在运行 Kimix 之前，需要配置以下环境变量（代码逻辑参考 `src/kimix/kimi_utils.py`）：

### 必需变量

| 变量名 | 说明 |
|--------|------|
| `KIMI_API_KEY` | **必需**。Kimi API 的访问密钥，必须以 `sk` 开头。若未设置或格式不正确，程序会报错并退出。 |

### 可选变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `KIMI_BASE_URL` | Kimi API 的基础 URL，必须以 `http` 开头。 | `https://api.kimi.com/coding/v1` |
| `KIMI_MODEL_NAME` | 指定使用的模型名称，必须以 `kimi` 开头。 | `kimi-for-coding` |

**示例（Linux / macOS）：**

```bash
export KIMI_API_KEY=sk-your-api-key
export KIMI_BASE_URL=https://api.kimi.com/coding/v1
export KIMI_MODEL_NAME=kimi-for-coding
```

**示例（Windows PowerShell）：**

```powershell
$env:KIMI_API_KEY="sk-your-api-key"
$env:KIMI_BASE_URL="https://api.kimi.com/coding/v1"
$env:KIMI_MODEL_NAME="kimi-for-coding"
```

---

## 五、CLI 基本用法

Kimix 的命令行接口分为「子命令」「启动参数」和「交互命令」三部分，以下内容整理自 `src/kimix/cli_impl/`。

### 5.1 子命令

除默认的交互式客户端外，`kimix` 还支持以下子命令：

| 子命令 | 说明 | 常用选项 |
|--------|------|----------|
| `serve` | 启动 Kimix HTTP 服务器（OpenCode 风格） | `--host`（默认 `127.0.0.1`）、`--port`（默认 `4096`） |
| `ssecli` | 启动 SSE CLI 调试器，连接 `kimix serve` 进行交互式测试。内部支持 `/new`、`/abort`、`/status`、`/sessions`、`/messages`、`/clear`、`/compact`、`/export`、`/help` 等命令；按 `Ctrl+C` 或输入 `EOF`（`Ctrl+D` / `Ctrl+Z`）退出 | `--host`、`--port`、`--debug`（打印 SSE 原始事件并保存为 `sse_log_<YYYYMMDD_HHMMSS>.txt`） |

**示例：**

```bash
# 启动 HTTP 服务
uv run kimix serve --port 4096

# 使用 SSE CLI 调试
uv run kimix ssecli --host 127.0.0.1 --port 4096 --debug
```

### 5.2 初始化 LLM 配置

Kimix 通过 JSON 配置文件初始化 LLM Provider。若启动时未通过 `--config` 指定自定义配置，将自动使用项目内置的默认配置（`src/kimix/default_config.json`）。

如果默认配置文件不存在，首次启动时会自动提示是否进行初始化；你也可以在交互终端中随时执行 `/init`，按提示逐项填写模型名称、类型、API Key、上下文长度、最大 token 数、思考力度（thinking effort）、模型能力（capabilities）、URL、温度等参数，配置将自动保存至 `src/kimix/default_config.json`：

```
/init
```

```json
{
    "model_name": "kimi-for-coding",
    "name": "moonshot",
    "model": "kimi-for-coding",
    "max_context_size": 262144,
    "capabilities": ["always_thinking"],
    "url": "https://api.kimi.com/coding/v1",
    "type": "kimi",
    "loop_control": {
        "max_steps_per_turn": 5000,
        "max_retries_per_step": 3,
        "max_ralph_iterations": 0,
        "reserved_context_size": 50000,
        "compaction_trigger_ratio": 0.85
    },
    "max_tokens": 128000,
    "show_thinking_stream": true,
    "thinking_effort": "low",
    "temperature": 1.0,
    "background": {
        "max_running_tasks": 4,
        "read_max_bytes": 30000,
        "notification_tail_lines": 20,
        "notification_tail_chars": 3000,
        "wait_poll_interval_ms": 500,
        "worker_heartbeat_interval_ms": 5000,
        "worker_stale_after_ms": 15000,
        "kill_grace_period_ms": 2000,
        "keep_alive_on_exit": false,
        "agent_task_timeout_s": 900,
        "print_wait_ceiling_s": 3600
    }
}
```

你也可以创建自定义配置文件并通过 `uv run kimix --config <path>` 加载。配置字段说明如下：

| 字段 | 必填 | 说明 |
|------|------|------|
| `type` | 是 | Provider 类型，可选值：`kimi`、`openai_legacy`、`openai_responses`、`anthropic`、`google_genai`、`gemini`、`vertexai` |
| `model` | 是 | 实际请求的模型名称 |
| `url` | 是 | API 基础地址 |
| `max_context_size` | 是 | 最大上下文长度（token 数），可选 `128k`、`200k`、`256k`、`512k`、`1M` |
| `model_name` | 否 | 模型别名，默认为 `unknown_model` |
| `name` | 否 | Provider 名称，默认为 `unknown` |
| `capabilities` | 否 | 模型能力列表，可选值：`thinking`、`always_thinking`、`image_in`、`video_in`。如 `["always_thinking"]` |
| `api_key` | 否 | API 密钥。若省略，将依次读取环境变量 `KIMI_API_KEY`、`KIMIX_API_KEY`。必须以 `sk` 开头 |
| `custom_headers` | 否 | 自定义 HTTP 请求头 |
| `oauth` | 否 | OAuth 配置，例如 `{"storage": "file", "key": "my-key"}` |
| `loop_control` | 否 | 循环控制参数，含 `max_steps_per_turn`、`max_retries_per_step`、`max_ralph_iterations`、`reserved_context_size`、`compaction_trigger_ratio` |
| `max_tokens` | 否 | 单次请求最大生成 token 数 |
| `show_thinking_stream` | 否 | 是否流式展示思考过程 |
| `thinking_effort` | 否 | 思考力度，可选 `off`、`low`、`medium`、`high`、`xhigh`、`max` |
| `temperature` | 否 | 采样温度，范围 `[0.0, 2.0]` |
| `background` | 否 | 后台任务相关配置 |

**自定义配置示例（参考 `docs/anthropic.json` 等）：**

```json
{
    "model_name": "my-model",
    "name": "my-name",
    "model": "minimax-m2.7",
    "max_context_size": 200000,
    "capabilities": ["thinking"],
    "url": "https://api.minimaxi.com/anthropic",
    "type": "anthropic",
    "api_key": "sk-xxx",
    "custom_headers": {},
    "oauth": {
        "storage": "file",
        "key": "my-key"
    }
}
```

### 5.3 启动参数

在启动 `kimix` 时，可附加以下选项来控制行为：

| 参数 | 说明 |
|------|------|
| `-c`, `--clean` | 退出时自动删除缓存文件 |
| `--no_think` | 关闭思考模式（thinking mode） |
| `--no_yolo` | 关闭 YOLO 模式 |
| `--no_color` | 关闭彩色输出 |
| `--manually-cot` | 开启手动 CoT 模式 |
| `--ralph` | 开启 Ralph 模式，可指定迭代次数（不传参数则为无限循环） |
| `-s`, `--skill-dir` | 指定自定义的 skill 目录（可多次使用以指定多个目录） |
| `--config` | 指定 JSON 格式的配置文件路径。若直接路径不存在，会依次在脚本所在目录的各级父目录中递归查找，最后在系统 `PATH` 中查找同名文件（格式可参考 `docs/*.json` 示例） |

**示例：**

```bash
uv run kimix --clean --manually-cot
```

### 5.4 交互命令

进入 Kimix 交互式终端后，可通过以下命令与 Agent 交互：

| 命令 | 说明 |
|------|------|
| `<path>` | 直接输入文件路径即可加载。非 `.py` 文件会分段解析为多行提示词；`.py` 文件则会直接执行脚本 |
| `/file:<path>` | 读取指定文件的全部内容作为单条提示词发送 |
| `/clear` | 清空当前对话上下文 |
| `/summarize` | 将对话上下文总结并写入记忆 |
| `/exit` | 退出程序 |
| `/help` | 显示帮助信息 |
| `/context` | 打印当前上下文的使用情况 |
| `/fix:<command>` | 运行一条命令，如果出错则自动尝试修复 |
| `/txt` | 进入多行文本输入模式（以 `/end` 结束，`/cancel` 取消） |
| `/init` | 交互式初始化默认 LLM 配置文件 |
| `/compact` | 压缩对话上下文 |
| `/export:<path>` | 导出当前会话消息到指定文件 |
| `/swarm` | 多 Agent 协作执行 Swarm 任务（以 `/end` 结束，`/cancel` 取消） |
| `/ralph:on` / `/ralph:off` / `/ralph:<num>` | 设置 Ralph 模式循环次数 |
| `/cot:on` / `/cot:off` | 开启 / 关闭手动 CoT 模式 |
| `/plan` | 使用 Agent 队列，执行长任务（支持 `/plan:<file>` 从文件加载任务描述） |
| `/script` | 编写并执行 Python 脚本（以 `/end` 结束输入） |
| `/cmd:<command>` | 执行系统命令 |
| `/cd:<path>` | 切换当前工作目录 |

除上述命令外，你也可以直接输入任意自然语言提示词（prompt）发送给 Agent 进行处理。
