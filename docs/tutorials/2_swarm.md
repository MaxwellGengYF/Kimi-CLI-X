# Agent Swarm 多智能体协作

Agent Swarm 通过协调者（Coordinator）将复杂任务拆分为有向无环图（DAG），并调度多个子 Agent 并行执行，最后合并结果。本文档介绍如何在 CLI 中使用 `/swarm` 命令调用该能力。

---

## 交互命令

进入 Kimix 交互终端后，执行：

```
/swarm
```

### 输入任务描述

执行后进入多行输入模式：

- 以 `/end` 结束输入并提交任务
- 以 `/cancel` 取消当前操作
- 空输入会被忽略并提示跳过

**示例**：

```text
/swarm
>>>> Start input multiple-lines for swarm task, end with /end, cancel with /cancel
请为这个项目生成单元测试，覆盖 src/utils.py 和 src/core.py 的核心函数
/end
```

### 执行流程

`_cmd_swarm` 内部按以下步骤执行（参考 `src\kimix\cli_impl\commands.py`）：

1. **收集提示词**：将多行文本拼接为完整任务描述 `task_prompt`。
2. **创建 Swarm 会话**：调用 `create_swarm_session(task_prompt)`，由协调者 Agent 根据 `agent_swarm.yaml` 规划 DAG 节点。
3. **执行 DAG**：使用 `Executor().execute(dag)` 按依赖关系调度各节点运行。
4. **输出结果**：执行完成后打印各节点返回结果；若任一阶段失败，打印对应错误信息。

---

## 状态与输出

| 场景 | 输出 |
|------|------|
| 创建 DAG 成功 | `Swarm session created, DAG has N node(s).` |
| DAG 执行完成 | `Swarm execution completed. Results: ...` |
| 空输入 | `Empty task prompt, skipping swarm command.` |
| 创建失败 | `Failed to create swarm session: ...` |
| 执行失败 | `Swarm execution failed: ...` |
| 取消操作 | `Swarm command cancelled.` |

---

## 典型场景

### 场景 A：批量代码审查

```text
/swarm
请审查 src/ 目录下所有 Python 文件的代码风格，找出潜在的性能瓶颈和安全隐患，并给出修改建议。
/end
```

协调者会为每个文件或模块创建独立节点，并行执行审查任务。

### 场景 B：多模块重构

```text
/swarm
将项目中的日志模块从 print 替换为标准 logging，涉及 utils.py、core.py 和 cli.py。
/end
```

协调者会按依赖顺序编排节点，先处理底层模块，再处理上层调用方。

---

## 注意事项

1. **耗时较长**：Swarm 任务涉及多次 LLM 调用与 DAG 调度，请耐心等待。
2. **结果合并**：子 Agent 的输出若涉及文件修改，最终会通过 VFS（虚拟文件系统）合并到统一目录；冲突时由协调者或额外会话仲裁。
3. **错误隔离**：单个节点失败不会阻塞其他独立节点，但最终结果中会包含错误信息。
