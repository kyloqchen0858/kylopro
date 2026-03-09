---
name: local-brain
description: "本地脑路由：决定何时用 L0 本地 Ollama 代替云 API，实现零成本自动化"
metadata: {"nanobot":{"always":true}}
---

# 本地脑路由守则（L0 决策层）

## 五层大脑架构（当前完整状态）

```
层级  标识       工具/模型                          成本      用途
────  ─────────  ─────────────────────────────────  ────────  ────────────────────────────
L0a  本地-通用  local_think(chat)  → qwen2.5:7b    ¥0/次    通用对话、文本分析、摘要、翻译
L0b  本地-代码  local_think(run_code) → deepseek-coder-v2:16b  ¥0/次    代码生成 + subprocess 执行
L0c  本地-推理  local_think(reason) → deepseek-r1:latest  ¥0/次    链式推理 (CoT)、财务分析、多步规划
L1   主力脑     deepseek-chat（当前会话 agent）     ¥/token  用户对话、任务调度、工具协调
L2   深度脑     deep_think → deepseek-reasoner      ¥¥/token 云端架构设计、根因分析（需要上下文）
L3   备用脑     minimax → Provider auto-fallback    ¥/token  L1 限流保护
────  ─────────────────────────────────────────────────────────────────────────────────────
心跳  HeartbeatService._decide  → qwen2.5:7b (OllamaProvider)  ¥0/次  每30分钟 skip/run 决策
```

**核心原则：能在 L0 完成的任务，不消耗云 API token。**

---

## L0 路由决策表

### 强制走 L0（不得用云 API）

| 场景 | mode | 自动选择的模型 |
|------|------|--------------|
| 财务运算（预算余额、%、费率计算） | `run_code` | deepseek-coder-v2:16b |
| 数学计算、单位换算 | `run_code` | deepseek-coder-v2:16b |
| 文件格式转换（JSON→Markdown、CSV 解析） | `run_code` | deepseek-coder-v2:16b |
| 日志过滤、正则提取、数据清洗 | `run_code` | deepseek-coder-v2:16b |
| 生成固定格式周报（读 cost_state.json 生成文本） | `run_code` | deepseek-coder-v2:16b |
| 链式财务分析（收支比、趋势、预测） | `reason` | deepseek-r1:latest |
| 多步规划（无需项目上下文时） | `reason` | deepseek-r1:latest |

### 优先走 L0（Ollama 运行时优先，不可用时切 L1）

| 场景 | mode | 自动选择的模型 |
|------|------|--------------|
| 技术文档摘要（无私有项目上下文） | `chat` | qwen2.5:7b |
| 中英/英中翻译 | `chat` | qwen2.5:7b |
| 代码注释、Docstring 生成 | `chat` | qwen2.5:7b |
| Shell 命令查询（通用 Linux/Windows 命令） | `chat` | qwen2.5:7b |
| 列表/字典操作、字符串处理 | `run_code` | deepseek-coder-v2:16b |

### 必须保留 L1/L2（云 API）

| 场景 | 原因 |
|------|------|
| 用户自然语言对话 | 需要人格一致性（SOUL.md）、记忆上下文（MEMORY.md） |
| 涉及项目历史 / 决策记忆的问答 | 本地模型无项目上下文 |
| 多工具协调任务（read_file + write_file + spawn） | 需要 nanobot AgentLoop 的完整 ReAct 循环 |
| 云端代码架构设计、深层 Bug 分析 | 用 deep_think → deepseek-reasoner |
| 任何用户直接提问 | 保持人格 (SOUL.md) 一致，L0 不接触用户 |

---

## HeartbeatService 集成（已激活）

心跳监测的 `_decide` 阶段（每 30 分钟读 HEARTBEAT.md，判断 skip/run）
**现在由本地 qwen2.5:7b 处理**，无需云 API。

配置方法（`~/.nanobot/config.json`）：
```json
{
  "gateway": {
    "heartbeat": {
      "enabled": true,
      "interval_s": 1800,
      "local_model": "qwen2.5:7b"
    }
  }
}
```

执行流程：
```
每 30 分钟：
  OllamaProvider(qwen2.5:7b)._decide(HEARTBEAT.md)
    → skip: 什么都不做（¥0）
    → run:  完整 AgentLoop 处理任务（调用 deepseek-chat，走 L1）
```

---

## SubagentManager 集成

SubagentManager.spawn() 使用 L1 云模型（deepseek-chat）执行多工具后台任务。
**L0 不替代 spawn**，两者职责不同：

| 机制 | 适用 | 执行路径 |
|------|------|---------|
| `local_think(run_code)` | 单次 Python 脚本、纯运算 | L0 → subprocess，同步，无工具调用 |
| `spawn` | 多工具协调、异步后台任务 | L1 → SubagentManager → nanobot mini-loop |

Kylo 决策规则：
```
任务能用一段 Python 代码完成？
  是 → local_think(run_code)   ← 零成本，秒级返回
  否（需要 read_file + web_fetch + write_file 等多工具）？
       → spawn                  ← 云 SubAgent，异步执行
```

---

## L0 调用模板（常用）

```
// 财务计算（用 run_code，deepseek-coder-v2:16b 自动执行）
local_think(
  prompt="计算本周 token 花费：input=3420 @ ¥0.002/K，output=890 @ ¥0.008/K，汇总",
  mode="run_code"
)

// cost_state.json 数据解析生成周报
local_think(
  prompt="读取 data/cost_state.json，生成可读的财务周报",
  mode="run_code",
  context="<cost_state.json 内容>"
)

// 链式推理分析
local_think(
  prompt="分析：本周已花费 ¥12，预算 ¥20，还剩 4 天，日均消耗趋势如何？是否需要节流？",
  mode="reason"
)

// 文本摘要（一般信息，无私有上下文）
local_think(
  prompt="用三句话总结以下技术文档的核心变更",
  mode="chat",
  context="<文档内容>"
)
```

---

## Ollama 不可用时的降级处理

`local_think` 返回 `⚠️ 本地 Ollama 服务未运行` 时：
1. **对用户的回复中顺带提示**（不单独报错）
2. **切换到 L1** 处理同一任务（云 API 成本增加，但任务不中断）
3. HeartbeatService 自动回退到云 provider（代码已处理，透明降级）

