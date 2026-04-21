# JSON-RPC 服务端

## 协议概述

`JSONRPCServer` 基于 TCP 实现 JSON-RPC 2.0 协议，默认监听 `127.0.0.1:8888`，支持多客户端并发连接。每个请求为单条 JSON 文本，服务器处理后立即返回对应的 JSON 响应。

## 通信格式

### 请求

```json
{
  "jsonrpc": "2.0",
  "method": "方法名",
  "params": [参数列表]
}
```

- `method`：要调用的远程方法名。
- `params`：可选，可为数组（位置参数）或对象（关键字参数）。

**注意**：服务端自动为所有已注册函数注入首个参数 `client_id`（整数，标识当前连接客户端），因此客户端请求中的参数从第二位开始传递。

### 响应

成功：

```json
{
  "jsonrpc": "2.0",
  "result": 返回值
}
```

失败：

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "错误描述"
  }
}
```

标准错误码：

| 错误码 | 含义 |
|--------|------|
| `-32700` | 解析错误（JSON 非法或编码错误） |
| `-32600` | 非法请求（非 JSON 对象） |
| `-32601` | 方法不存在 |
| `-32602` | 参数非法（类型或数量不匹配） |
| `-32603` | 内部错误（调用异常） |

## 服务端接口

### 注册方法

- `register(name, func)` — 以指定名称注册函数。
- `register_function(func)` — 以函数 `__name__` 自动注册。

### 生命周期

- `start(blocking=True)` — 启动 TCP 服务器。
- `stop()` — 停止服务器。

### 客户端管理

- `get_client_count()` — 当前连接数。
- `get_client_ids()` — 已连接客户端 ID 列表。
- `disconnect_client(client_id)` — 断开指定客户端。
- `wait_for_connection(timeout=5.0)` — 等待至少一个客户端接入。
- `wait_for_disconnection(timeout=5.0)` — 等待所有客户端断开。

### WebSocket 桥接（可选）

- `start_websocket_server(ws_port, blocking=False)` — 启动 WebSocket 服务器，将消息透传至后端 TCP JSON-RPC 服务。需安装 `websockets`。
- `stop_websocket_server()` — 关闭 WebSocket 服务。

## 命令行启动参数

通过 CLI 启动服务端时，可使用以下参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--server` | `False` | 启用服务器模式（必填） |
| `--host` | `127.0.0.1` | 绑定主机地址 |
| `--port` | `8888` | 绑定 TCP 端口 |
| `--ws-port` | `None` | WebSocket 桥接端口（可选） |

示例：

```bash
uv run kimix --server --host 0.0.0.0 --port 8888 --ws-port 8889
```

## 使用示例

```python
from kimix.network.rpc_server import JSONRPCServer

server = JSONRPCServer(host="127.0.0.1", port=8888)

# 注册函数；首个参数 client_id 由服务端自动注入
def add(client_id, a, b):
    return a + b

server.register_function(add)
server.start(blocking=True)
```
