# 飞书机器人创建指南

本指南介绍如何创建一个飞书自定义机器人，供 Kimix Lark Bot 使用。

## 1. 进入飞书开放平台

打开 [飞书开放平台](https://open.feishu.cn/app) 并登录。

## 2. 创建企业自建应用

1. 点击右上角 **"创建企业自建应用"**
2. 填写应用名称，例如 `KimixBot`
3. 选择应用头像（可选）
4. 点击 **"确定创建"**

## 3. 获取 App ID 和 App Secret

1. 进入应用详情页，左侧菜单点击 **"凭证与基础信息"**
2. 在页面中找到：
   - **App ID**（格式如 `cli_xxxxxxxxxxxxxxxx`）
   - **App Secret**（点击"查看"按钮显示）
3. 将这两个值记下来，稍后在 Kimix Lark Bot 配置中使用

## 4. 配置机器人能力

1. 左侧菜单点击 **"机器人"**
2. 打开 **"启用机器人"** 开关
3. 填写机器人基本信息：
   - 机器人名称：`Kimix Bot`
   - 描述：`管理本地 Kimix 进程的飞书机器人`
4. 点击 **"保存"**

## 5. 配置权限

1. 左侧菜单点击 **"权限管理"**
2. 在 **"权限配置"** 标签页中，搜索并添加以下权限：
   - `im:message:send_as_bot` — 以机器人身份发送消息
   - `im:message.group_msg` — 接收群消息
   - `im:chat:readonly` — 获取群组信息
   - `im:message` — 读取用户单聊消息
3. 点击 **"批量开通"** 或逐个点击 **"开通权限"**

## 6. 配置事件订阅

1. 左侧菜单点击 **"事件与回调"**
2. 打开 **"启用事件"** 开关
3. 在 **"请求地址配置"** 中：
   - 由于 Kimix Lark Bot 使用 **长连接（WebSocket）** 接收事件，**无需配置 HTTP 请求地址**
   - 确保 **"加密密钥"** 留空（或随意填写，Bot 不使用加密模式）
4. 在 **"订阅事件"** 中添加以下事件：
   - `接收消息` (im.message.receive_v1)
   - `进入会话` (im.chat.access_event.bot_p2p_chat_entered_v1)
5. 点击 **"保存"**

## 7. 发布应用

1. 左侧菜单点击 **"版本管理与发布"**
2. 点击 **"创建版本"**
3. 填写版本信息：
   - 版本号：`1.0.0`
   - 更新说明：`初始化版本`
4. 点击 **"保存"**
5. 点击 **"申请发布"**
6. 让你的企业管理员审批通过

## 8. 将机器人添加到群聊或单聊

### 单聊
在飞书搜索你创建的机器人名称（如 `KimixBot`），点击即可开始单聊。

### 群聊
1. 进入目标群聊
2. 点击群设置 → **"群机器人"**
3. 点击 **"添加机器人"**
4. 搜索并选择你的机器人
5. 点击 **"添加"**

## 9. 配置 Kimix Lark Bot

首次运行 Kimix Lark Bot 时，如果未检测到配置文件，会交互式要求输入 App ID 和 App Secret：

```bash
kimix_lark_bot
```

或者手动创建配置文件 `~/.kimix_lark_bot.yaml`：

```yaml
app_id: "cli_xxxxxxxxxxxxxxxx"
app_secret: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

projects:
  - slug: "myproject"
    path: "~/projects/myproject"
    label: "My Project"
```

然后再次运行：

```bash
kimix_lark_bot
```

## 常见问题

**Q: 机器人没有回复消息？**  
A: 检查以下几点：
1. 确认已开通 `im:message` 和 `im:message:send_as_bot` 权限
2. 确认已订阅 `im.message.receive_v1` 事件
3. 确认应用已发布并通过审批
4. 检查 Kimix Lark Bot 控制台输出的 App ID 是否正确

**Q: 如何获取 chat_id？**  
A: 在 Kimix Lark Bot 运行时，向机器人发送任意消息，控制台会打印 `chat_id`。或者使用飞书开放平台的 API 调试工具查询。
