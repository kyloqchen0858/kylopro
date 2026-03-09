# Kylopro 是如何建立在 nanobot 之上的

## 一句话说明

Kylopro 不是脱离 nanobot 的新 Agent 框架，而是一个基于 nanobot 深度定制出来的开发型助手。

## 为什么要基于 nanobot 开发

nanobot 已经提供了一个足够轻量且可改造的底座：

- 有现成的 Provider 体系，可以统一接入不同模型
- 有现成的 AgentLoop，可以处理工具调用循环
- 有原生 Tool 抽象，便于注入自定义能力
- 有 `SKILL.md` 机制，可以给助手注入规则和流程
- 有 Telegram 等 channel，不需要重复造轮子

如果 Kylopro 在外面再包一层自己的 Provider、Loop、Router，短期看起来灵活，长期会出现几个问题：

- 配置分裂：一部分读 `.env`，一部分读 `config.json`
- 模型分裂：一部分走自研客户端，一部分走 nanobot Provider
- 工具分裂：一部分工具 nanobot 看不见，一部分技能 Kylopro 看不见
- 调试困难：出现问题时很难判断到底是哪一层出错

所以当前路线已经切换为：尽量把增强能力落到 nanobot 原生链路里。

## Kylopro 现在复用了 nanobot 的哪些部分

### 1. Provider 与模型路由

Kylopro 现在以 nanobot 的 Provider 体系为底座。模型配置来自 `~/.nanobot/config.json`，而不是 Kylopro 单独维护另一套真实配置。

当前主方向：

- 默认模型走 MiniMax
- 后续按任务类型切换到其他模型
- 减少外层独立 provider 带来的重复维护

### 2. AgentLoop

真正处理消息、工具调用和上下文拼接的是 nanobot 的 `AgentLoop`。Kylopro 的增强工作主要围绕这条链路展开，例如：

- 给工作区注入自定义工具
- 给系统提示注入 `SOUL.md`
- 给助手注入额外技能说明

### 3. Tool 系统

Kylopro 的任务收件箱、深度分析之类的能力，应该尽量写成 nanobot 原生 `Tool` 子类，再注册到 `ToolRegistry` 中。

这样做的好处是：

- LLM 可以直接看到这些工具
- 调用方式统一
- 错误处理和参数校验统一
- 后续更容易维护

### 4. Skills 机制

Kylopro 的行为规则和开发流程，不再只放在单独的 Python 代码里，也通过 nanobot 的 `SKILL.md` 机制注入。

这让助手在运行时可以同时获得：

- 身份规则
- 开发习惯
- 任务收件箱使用规范
- 工作区结构说明

### 5. 工作区与文件边界

这次调整里，一个很重要的修复是把实际工作区固定到 `Kylopro-Nexus/workspace/`，并开启工作区限制。这样做的目的很直接：

- 生成的文件不再乱落到桌面
- 输出目录、沙盒目录、任务目录边界更清楚
- 工具执行行为更稳定

## Kylopro 的基础功能概览

### 开发协作

- 读取和修改项目文件
- 执行命令行命令
- 生成脚本和说明文档
- 协助排查 bug 和推进开发任务

### 任务管理

- 将需求转成任务文件
- 管理任务状态
- 支持异步任务推进

### 模型协作

- 通过 nanobot Provider 接多模型
- 为复杂问题预留深度推理入口

### 远程通道

- 通过 Telegram 接收消息
- 后续扩展关键进展同步

### 可扩展性

- 可继续增加 Tool 子类
- 可继续增加 `SKILL.md`
- 可继续沿着 nanobot 原生机制扩展，而不是重复造框架

## 当前阶段的结论

Kylopro 最合理的形态，不是一个和 nanobot 平行竞争的系统，而是：

> 一个建立在 nanobot 之上的、面向开发与自动化场景的专用助手层。

这个方向的好处是清晰、可维护，也更适合持续迭代。