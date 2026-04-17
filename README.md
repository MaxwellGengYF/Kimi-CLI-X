# Kimi Agent CLI

Kimi Agent CLI 是一个交互式命令行工具，用于与 Kimi AI Agent 进行交互。它提供了丰富的功能，包括文件操作、代码执行、任务管理、技能加载等。

> 想了解更多 Kimi-CLI-X 的优势与改进，请参阅 [why_us.md](docs/why_us.md)。

## 特性介绍

### 1. 交互式对话
- 支持多轮对话，保持上下文记忆
- 可清除对话历史 (`/clear`)
- 支持多行文本输入 (`/txt`)

### 2. 扩展工具

#### 文件操作
- **WriteFile**: 写入文件内容（带格式验证）
- **ReadFile**: 读取文件内容
- **StrReplaceFile**: 替换文件中的字符串
- **Glob**: 查找文件（支持通配符）
- **Grep**: 搜索文件内容
- **Ls**: 目录列表
- **Mkdir**: 创建目录
- **Rm**: 删除文件/目录

#### 代码与执行
- **Python**: 执行 Python 代码
- **Run**: 运行可执行文件（支持后台模式和输入模式）
- **Input**: 向后台进程发送输入
- **Cpplint**: C++ 语法检查（使用 clangd）

#### 后台任务管理
- **TaskList**: 列出后台任务
- **TaskOutput**: 获取后台任务输出
- **TaskStop**: 停止后台任务

#### 文档处理
- **Docx2md**: Word 文档转 Markdown
- **Pdf2md**: PDF 转 Markdown

#### 网络与搜索
- **SearchWeb**: 网络搜索
- **FetchURL**: 获取网页内容

#### 任务与计划
- **SetTodoList**: 设置待办事项列表
- **EnterPlanMode**: 开启计划模式
- **ExitPlanMode**: 关闭计划模式

#### 技能与代理
- **GrepAnalyzer**: 语义搜索工具（比 Grep 更适合相关搜索）
- **Spawn**: 创建子代理处理特定任务

#### 其他
- **Setflag**: 设置线程本地标志值

### 3. 代码执行
- **Python**: 执行 Python 代码
- **Run**: 运行可执行文件（支持输入模式）
- **Cpplint**: C++ 语法检查（使用 clangd）

### 4. 自动化功能
- **Ralph 模式** (`--ralph`): 自动循环工作直到任务完成
- **自动修复** (`/fix`): 运行命令并自动修复错误
- **验证功能** (`/validate`): 验证条件是否为真

### 5. 开发工具
- 内置构建脚本 (`toolbox_build_cli.py`)
- 支持包管理和依赖安装
- 支持创建分发包

---

## 应用方法

### 环境配置

设置以下环境变量：

```bash
# 必需：LLM Model API Key
set KIMI_API_KEY=your_api_key_here

# 可选：API 基础地址（默认：https://api.kimi.com/coding/v1）
set KIMI_BASE_URL=https://api.kimi.com/coding/v1

# 可选：模型名称
set KIMI_MODEL_NAME=kimi-for-coding
```

### 启动 CLI

```bash
# 基本用法
python cli.py

# 清理模式（退出时删除缓存）
python cli.py -c
python cli.py --clean

# Ralph 自动循环模式（自动循环工作直到完成）
python cli.py --ralph

# 禁用思考模式
python cli.py --no_think

# 启用计划模式
python cli.py --plan

# 禁用 YOLO 模式（更安全，需要确认危险操作）
python cli.py --no_yolo

# 禁用彩色输出
python cli.py --no_color

# 指定自定义技能目录（可指定多个）
python cli.py -s ./my_skills
python cli.py --skill-dir ./skills1 ./skills2

# 组合多个选项
python cli.py -c --ralph --no_yolo
```

### 交互命令

启动后，你可以使用以下命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/clear` | 清除对话上下文 |
| `/context` | 显示当前上下文使用统计 |
| `/exit` | 退出程序 |
| `/skill:<name>` | 加载指定技能 |
| `/file:<path>` | 加载并执行文件内容（逐行执行） |
| `<path>` | 同 `/file:<path>`，直接输入文件路径 |
| `/txt` | 输入多行文本（以 `/end` 结束，`/cancel` 取消） |
| `/script` | 输入并执行 Python 脚本（以 `/end` 结束） |
| `/cmd:<command>` | 执行系统命令 |
| `/cd:<path>` | 切换工作目录 |
| `/summarize` | 总结对话上下文到记忆 |
| `/validate:<prompt>` | 验证条件是否为真 |
| `/fix:<command>` | 运行命令并自动修复错误 |
| `/tool:<name>` | 运行 tools/ 目录下的脚本 |
| `/tool:help` | 列出所有可用工具 |
| `/tool:graph` | 生成项目分析图表（思维导图、文档） |
| `/think:on/off` | 开启/关闭思考模式 |
| `/plan:on/off` | 开启/关闭计划模式 |
| `/ralph:on/off` | 开启/关闭 Ralph 自动循环模式 |
| `/md:on/off` | 开启/关闭读取 AGENTS.md |

### 使用示例

#### 1. 基本对话
```
>>>>>>>>> Enter your prompt or command:
写一个 Python 函数计算斐波那契数列
```

#### 2. 执行 Python 文件
```
>>>>>>>>> Enter your prompt or command:
/file:script.py
```

或者直接输入文件路径：
```
>>>>>>>>> Enter your prompt or command:
script.py
```

#### 3. 执行 Python 脚本
```
>>>>>>>>> Enter your prompt or command:
/script
>>>> Start input multiple-lines, end with /end
print("Hello, World!")
/end
```

#### 4. 执行系统命令
```
>>>>>>>>> Enter your prompt or command:
/cmd:ls -la
```

#### 5. 加载技能
```
>>>>>>>>> Enter your prompt or command:
/skill:python-dev
```

#### 6. 运行命令并自动修复
```
>>>>>>>>> Enter your prompt or command:
/fix:python my_script.py
```

#### 7. 验证条件
```
>>>>>>>>> Enter your prompt or command:
/validate:Python 是解释型语言吗？
```

#### 8. 多行文本输入
```
>>>>>>>>> Enter your prompt or command:
/txt
>>>> Start input multiple-lines, end with /end
这是第一行
这是第二行
这是第三行
/end
```

### Python API 用法

你也可以在自己的 Python 脚本中使用 `kimi_utils.py`：

```python
from kimi_utils import prompt, create_session, close_session, fix_error

# 简单提示（自动创建临时会话）
prompt("写一个计算斐波那契数列的函数")

# 使用持久化会话
session = create_session("my-session")
prompt("解释递归", session=session)
prompt("给我一个例子", session=session)  # 保持上下文
close_session(session)

# 自动修复错误
fix_error("python my_script.py")
```

### 构建脚本使用

```bash
# 安装项目依赖
python toolbox_build_cli.py build <project_dir>

# 复制本地包到 site-packages
python toolbox_build_cli.py copy <sdk_repo> <cli_repo> <packages_path>

# 创建分发包
python toolbox_build_cli.py package ./dist --output-name myproject-v1.0
```

---

## Project Analysis & Mind-Map Generation System

The `graph/` module provides an automated project analysis system that generates comprehensive mind-maps, API documentation, and RAG-friendly keyword indices from codebases.

### Features

- **Multi-Language Support**: Python, C++, C, Lua, CMake, JSON, YAML, TOML
- **Gitignore-Aware**: Respects `.gitignore` patterns during traversal
- **Batch Analysis**: Processes files in batches with isolated sessions for efficient context management
- **Smart Output**: Generates mind-maps, API references, and keyword indices

### Generated Outputs

| File | Description |
|------|-------------|
| `mindmap.md` | Hierarchical project architecture visualization |
| `project_summary.md` | Detailed project overview with APIs and entry points |
| `ANALYSIS_REPORT.md` | Analysis statistics and language distribution |
| `keywords.json` / `keywords_rag.json` | Extracted keywords for RAG systems |
| `api_reference.json` | API documentation index |
| `index.json` | Master index of all analyses |
| `analyses/` | Individual file analysis results |

### Usage

#### Using `/tool:graph` command (Recommended)

```
>>>>>>>>> Enter your prompt or command:
/tool:graph /path/to/project --batch-size 5
```

Or inside the CLI:
```
/tool:graph
>>>> Input cmd:
/path/to/project --batch-size 5 --mode batch
```

#### Using Python module directly

```bash
# Basic usage - analyze current directory
python -m graph.main /path/to/project

# Specify batch size (files per analysis batch)
python -m graph.main /path/to/project --batch-size 5

# Use different analysis modes
python -m graph.main /path/to/project --mode single    # Analyze files individually
python -m graph.main /path/to/project --mode batch     # Analyze in batches (default)
python -m graph.main /path/to/project --mode mixed     # Mixed strategy

# Custom output directory
python -m graph.main /path/to/project --output ./my-docs

# Adjust batch line limit
python -m graph.main /path/to/project --batch-size 3 --max-lines 500

# Example: Analyze RoboCute project
python -m graph.main D:/RoboCute --batch-size 5 --mode batch
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `project_path` | Path to project directory to analyze | (required) |
| `--output, -o` | Output directory for analysis results | `[project]/agent_doc` |
| `--batch-size, -b` | Maximum files per batch | 5 |
| `--max-lines, -l` | Maximum lines per batch | 500 |
| `--mode, -m` | Analysis mode: `single`, `batch`, `mixed` | `batch` |
| `--verbose, -v` | Enable verbose output | False |

### Architecture

```
graph/
├── main.py              # CLI entry point
├── project_analyzer.py  # Gitignore-aware project traversal
├── analysis_engine.py   # Core analysis with session management
├── output_manager.py    # Result formatting and output
└── prompts.py           # Analysis prompt templates
```

### How It Works

1. **Project Traversal**: Scans the project directory, respecting `.gitignore` patterns
2. **File Classification**: Separates config files (CMakeLists.txt, pyproject.toml, etc.) from code files
3. **Batch Processing**: Creates independent sessions for each batch to manage context
4. **Context Compaction**: Uses `summarize_session()` after each batch to prevent context overflow
5. **Output Generation**: Saves results to `[project]/agent_doc/` directory

---

## 注意事项

- 只有 `.py` 文件可以通过 `/file` 命令直接执行
- CLI 会保持对话上下文直到使用 `/clear` 清除
- 每次 AI 响应后会显示上下文使用情况
- 按 `Ctrl+C` 可随时中断当前操作或退出 CLI
- 使用 YOLO 模式时，危险操作会自动确认，请谨慎使用

---

## 项目结构

```
kimi-agent/
├── cli.py      # 主 CLI 入口
├── kimi_utils.py          # Python API 工具函数
├── agent_utils.py         # Agent 工具函数
├── toolbox_build_cli.py   # 构建脚本
├── BUILD.md               # 详细构建文档
├── agent_boss.yaml        # Agent 基础配置
├── agent_worker.yaml      # Agent 工作配置
├── kaos/                  # Kaos 路径库
├── kosong/                # Kosong 工具库
├── kimi_cli/              # CLI 核心包
├── kimi_agent_sdk/        # Kimi Agent SDK
├── my_tools/              # 自定义工具
└── tools/                 # 工具脚本目录
```
