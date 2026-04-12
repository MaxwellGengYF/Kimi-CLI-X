# Kimi Agent CLI

Kimi Agent CLI 是一个交互式命令行工具，用于与 Kimi AI Agent 进行交互。它提供了丰富的功能，包括文件操作、代码执行、任务管理、技能加载等。

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
python kimi_agent_cli.py

# 清理模式（退出时删除缓存）
python kimi_agent_cli.py -c

# Ralph 自动循环模式
python kimi_agent_cli.py --ralph

# 启用思考模式
python kimi_agent_cli.py --think

# 初始启用计划模式（Agent Model会自行决定）
python kimi_agent_cli.py --plan

# 禁用 YOLO 模式（更安全，需要确认危险操作）
python kimi_agent_cli.py --no_yolo

# 指定自定义技能目录
python kimi_agent_cli.py -s ./my_skills

# 组合多个选项
python kimi_agent_cli.py -c --ralph --no_yolo
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
| `/file:<path>` | 加载并执行文件 |
| `/txt` | 输入多行文本（以 `/end` 结束） |
| `/script` | 输入并执行 Python 脚本 |
| `/cmd` | 执行系统命令 |
| `/summarize` | 总结对话上下文到记忆 |
| `/validate:<prompt>` | 验证条件是否为真 |
| `/fix:<command>` | 运行命令并自动修复错误 |
| `/tool:<name>` | 运行 tools/ 目录下的脚本 |
| `/think:on/off` | 开启/关闭思考模式 |
| `/plan:on/off` | 开启/关闭计划模式 |
| `/ralph:on/off` | 开启/关闭 Ralph 自动循环模式 |
| `/md:on/off` | 开启/关闭读取 AGENTS.md |
| `/cd:<path>` | 切换工作目录 |

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
/cmd
>>>> Input cmd:
ls -la
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
├── kimi_agent_cli.py      # 主 CLI 入口
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
