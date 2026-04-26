# Kimix Lark Bot

一个 CLI 飞书 Bot，用于管理电脑中的 Kimix 进程。

## 功能

- 通过飞书消息启动/停止 Kimix server 进程
- 管理多个工作区（workspace）
- 在飞书中直接与 Kimix 会话交互
- 支持项目快捷名（slug）
- 首次运行自动引导配置

## 安装

```bash
cd kimix_lark_bot
uv tool install -e .
```

安装完成后，命令 `kimix_lark_bot` 将全局可用。

## 配置

### 首次运行（交互式配置）

直接运行命令，如果没有配置文件，会交互式询问 App ID 和 App Secret：

```bash
kimix_lark_bot
```

配置将自动保存到 `~/.kimix_lark_bot.yaml`。

### 手动配置

你也可以手动创建配置文件：

```bash
cp config.example.yaml ~/.kimix_lark_bot.yaml
# 编辑 ~/.kimix_lark_bot.yaml 填写飞书凭证
```

或使用自定义配置文件：

```bash
kimix_lark_bot -c /path/to/bot.yaml
```

### 配置示例

```yaml
app_id: "cli_xxxxxxxxxxxxxxxx"
app_secret: "your-app-secret"

projects:
  - slug: "myproject"
    path: "~/projects/myproject"
    label: "My Project"
```

## 创建飞书机器人

参见 [docs/setup_feishu_bot.md](docs/setup_feishu_bot.md)。

## 启动

```bash
# 使用默认配置 ~/.kimix_lark_bot.yaml
kimix_lark_bot

# 使用自定义配置
kimix_lark_bot -c bot.yaml
```

## 指令

| 指令 | 说明 |
|------|------|
| `帮助` / `help` | 显示帮助 |
| `状态` / `status` | 查看 Kimix 进程状态 |
| `启动 <项目名>` | 启动 Kimix server |
| `停止 <项目名>` | 停止 Kimix server |
| `!退出` | 退出当前工作区 |

在工作区模式下，直接发送消息即可与 Kimix 交互。

## 架构

类似 `sail_bot`，但管理的是 `kimix server` 进程：

- **KimixProcessManager**: 管理 kimix server 进程生命周期
- **KimixSessionClient**: 通过 JSON-RPC TCP 或 WebSocket 与 kimix server 通信
- **FeishuBotAgent**: 飞书 Bot 主入口，处理消息事件
- **BotBrain**: 意图识别，支持关键词匹配

## Kimix 通信接口

Kimix server 提供 JSON-RPC TCP 接口：

- `open_session(client_id)` -> session_id
- `close_session(client_id, session_id)` -> "ok"
- `input_from_client(client_id, session_id, text)` -> "processing"
- `get_output_from_client(client_id, session_id)` -> list[str]
- `is_session_finished(client_id, session_id)` -> bool

支持通过 `--ws-port` 启动 WebSocket bridge，Bot 可自动选择 TCP 或 WebSocket 连接。
