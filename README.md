# Kimi-CLI-X 文档中心

欢迎来到 Kimi-CLI-X（Kimix）的文档仓库。这里汇集了项目的核心说明、教程与配置参考，帮助你快速上手并深度掌握 Kimix 的使用与扩展。

想了解更多 Kimi-CLI-X 的优势与改进，请参阅 [why_us.md](docs/why_us.md)。

---

## 文档索引

### 概述

| 文档 | 简介 |
|------|------|
| [`docs/why_us.md`](docs/why_us.md) | 介绍 Kimi-CLI-X 相比原版的核心优化与新增能力，包括提示词精简、权限校验、并发架构、文档转换、脚本系统、超轻量 RAG 等。 |

### 教程系列

| 文档 | 简介 |
|------|------|
| [`docs/tutorials/1_quick_start.md`](docs/tutorials/1_quick_start.md) | **快速入门指南**。涵盖 Git Submodule 拉取、`uv` 环境安装、CLI 启动参数与交互命令的完整说明。 |
| [`docs/tutorials/2_manager.md`](docs/tutorials/2_manager.md) | **Manager 深度解析**。从源码层面剖析 `kimix_manager` 的三大核心模块（`company.py`、`designer.py`、`base.py`），讲解任务编排、Worker 并发调度、Designer/Programmer 双分支模式及完整工作流示例。 |
| [`docs/tutorials/3_builtin_tools.md`](docs/tutorials/3_builtin_tools.md) | **内置工具完全指南**。系统介绍 Agent 的全部内置工具（文件 I/O、搜索、代码执行、进程管理、文档转换、计划模式、子代理等），并给出提示词引导策略与最佳实践。 |
| [`docs/tutorials/4_skills.md`](docs/tutorials/4_skills.md) | **自定义 Skill 编写教程**。讲解 Skill 的设计原则、目录结构、`SKILL.md` 编写规范、附属资源组织方式、测试打包流程及安装使用方法。 |

### 配置参考

| 文件 | 简介 |
|------|------|
| [`docs/config.json`](docs/config.json) | 模型配置示例文件，包含 `model`、`url`、`api_key`、`capabilities` 等字段，可供编写自定义配置时参考。 |

---

## 推荐阅读路径

1. **新用户**：从 [`1_quick_start.md`](docs/tutorials/1_quick_start.md) 开始，完成环境准备与基本使用。
2. **想深入理解架构**：阅读 [`2_manager.md`](docs/tutorials/2_manager.md)，了解任务是如何被拆解、调度与执行的。
3. **优化提示词效果**：参考 [`3_builtin_tools.md`](docs/tutorials/3_builtin_tools.md)，学会精准引导 Agent 调用工具。
4. **扩展 Agent 能力**：跟随 [`4_skills.md`](docs/tutorials/4_skills.md)，编写并分发自定义的 Skill。
