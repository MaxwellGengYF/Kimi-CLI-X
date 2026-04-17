# Kimix 快速入门指南

本文档将带你完成 Kimix 的环境准备、安装以及 CLI 的基本使用。

---

## 一、Git Submodule 的拉取

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

## 二、使用 uv 安装与运行

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

## 三、CLI 基本用法

Kimix 的命令行接口分为「启动参数」和「交互命令」两部分，以下内容整理自 `src\kimix\cli.py`。

### 3.1 启动参数

在启动 `kimix` 时，可附加以下选项来控制行为：

| 参数 | 说明 |
|------|------|
| `-c`, `--clean` | 退出时自动删除缓存文件 |
| `--ralph` | 开启自动循环模式，持续工作直到任务完成（注意 Token 消耗） |
| `--no_think` | 关闭思考模式（thinking mode） |
| `--plan` | 开启计划模式（plan mode） |
| `--no_yolo` | 关闭 YOLO 模式 |
| `-s`, `--skill-dir` | 指定自定义的 skill 目录（可多次使用以指定多个目录） |
| `--config` | 指定 JSON 格式的配置文件路径（可参考 `config_example.json`） |

**示例：**

```bash
uv run kimix --plan --clean
```

### 3.2 交互命令

进入 Kimix 交互式终端后，可通过以下命令与 Agent 交互：

| 命令 | 说明 |
|------|------|
| `/file:<path>` | 加载指定文件并逐行执行其内容 |
| `<path>` | 等价于 `/file:<path>`，直接输入文件路径即可加载 |
| `<xxx>.py` | 直接输入 Python 脚本文件名，可在提示词框原地执行该脚本 |
| `/clear` | 清空当前对话上下文 |
| `/summarize` | 将对话上下文总结并写入记忆 |
| `/exit` | 退出程序 |
| `/skill` | 加载 skills |
| `/help` | 显示帮助信息 |
| `/context` | 打印当前上下文的使用情况 |
| `/validate:<prompt>` | 测试给定条件是否为真 |
| `/fix:<command>` | 运行一条命令，如果出错则自动尝试修复 |
| `/txt` | 进入多行文本输入模式（以 `/end` 结束，`/cancel` 取消） |
| `/think:on` / `/think:off` | 开启 / 关闭思考模式（需要 LLM 支持） |
| `/plan:on` / `/plan:off` | 开启 / 关闭计划模式 |
| `/ralph:on` / `/ralph:off` | 开启 / 关闭 Ralph 自动循环模式 |
| `/script` | 编写并执行 Python 脚本（以 `/end` 结束输入） |
| `/cmd:<command>` | 执行系统命令 |
| `/cd:<path>` | 切换当前工作目录 |

除上述命令外，你也可以直接输入任意自然语言提示词（prompt）发送给 Agent 进行处理。
