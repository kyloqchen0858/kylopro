# Kylopro 开发原则

> **核心理念**: 开发过程本身就是训练数据。每次排障、每次改动都在增强 Kylo 的自我认知。
> **Phase 11+ 更新 (2026-03-09)**: 补充任务锚定、生产优先、脑体闭环、认知更新、凭证硬边界五条原则。

---

## 原则一：以任务为锚，不以技术为锚

每个开发 Phase 必须以「Kylo 能完成 X 任务」作为验收标准，而不是「X 模块实现了 Y 功能」。

- ❌ 错：「BrainHooks 成功把 HOT 记忆注入 prompt」
- ✅ 对：「Kylo 今天能在飞书里创建文档并发消息通知用户，不需要我手动操作 token」

验收公式：**用户可观测到的外部效果 = 完成**，内部管线打通但无外部效果 ≠ 完成。

## 原则二：生产优先，研发跟随

先让 Kylo 真实完成外部任务，再回来优化算法和架构。大脑需要真实数据，不是测试数据。

- 接下来的目标：飞书发消息 → Notion 更新页面 → 更多平台
- 真实操作的 episodes 比重新设计算法更有价值
- 不要在没有生产数据的情况下调优元认知算法

## 原则三：大脑和身体都不能脱离骨架

所有能力必须通过 nanobot 骨架暴露：`SKILL.md` 定义 → `Tool` 注册 → `AgentLoop` 调用。

- 不能绕过这个链路，即使是「临时测试」也不行
- **原因：绕过骨架的能力不会被 episode 记录，大脑学不到东西**
- Python 文件存在但没有 `SKILL.md` = Kylo 不知道自己有这个能力

## 原则四：每次开机必须有认知更新

Kylo 每次启动时应该知道：「我上次更新了什么，今天能做什么新事情」。

- 启动差分注入：`brain_hooks.py` 对比 DEVLOG 最新变化
- 新能力上线后，SOUL.md / AGENTS.md / SKILL.md 同步更新
- 目标：重启后模型立即理解新增能力，无需用户手动告知

## 原则五：凭证是硬边界，记忆是软边界

任何 token、密钥、API key 只进 `CredentialVault`，绝不出现在：

- WARM/HOT/COLD 记忆正文
- Telegram / QQ 消息
- 任何日志文件
- episode outcome 字段

这条规则需要在代码层面有对应的 guard（`auth_middleware.py` 的 outcome 截断），不能只靠模型自觉。

---

## 原则六：开发即训练

每一次开发迭代都产生三类可复用知识：

1. **排障记录** → `docs/debug/` — 完整的思考过程、误判路径、最终根因
2. **技能沉淀** → `skills/*/` — 从排障中提炼出的可被 Kylo 直接调用的操作手册
3. **认知更新** → `SOUL.md` + `AGENTS.md` — 身体模型、物理限制、行为边界

```
Bug/Feature → [排障/开发] → Debug Log → Skill → Soul Update
                ↓                                    ↓
            DEVLOG.md                          Kylo 下一次更聪明
```

## 原则七：先理解再改动

- **读代码 before 改代码**: 不对未读过的文件提交修改
- **隔离测试法优先**: 关闭所有变量，逐个启用，二分定位
- **不要被时序相关性误导**: A 和 B 同时发生 ≠ A 导致了 B

## 原则八：身体认知

Kylo 必须理解自己的物理运行环境：

| 层级 | 含义 | 例子 |
|------|------|------|
| 大脑 | LLM 提供商 | DeepSeek / MiniMax / Ollama |
| 骨架 | nanobot gateway | asyncio event loop, 单进程 |
| 四肢 | tools + channels | 文件操作、终端、Telegram、QQ |
| 神经 | bus + session | MessageBus 消息路由 |
| 皮肤 | venv + 依赖 | Python 3.12 venv launcher 行为 |

**关键认知**: 
- Windows venv python.exe 是 launcher，spawn Python312 子进程是正常行为
- gateway 进程数 = 2（launcher + worker）是预期的
- `sys.executable` vs `sys._base_executable` 区别必须了解

## 原则九：文档即记忆

| 文档 | 更新频率 | 内容 |
|------|----------|------|
| `DEVLOG.md` | 每个 Phase | 开发日志，跨对话恢复上下文 |
| `DEVELOPMENT_ROADMAP.md` | Phase 完成时 | 宏观路线图 |
| `docs/debug/*.md` | 每次重大排障 | 排障全过程记录 |
| `skills/*/SKILL.md` | 新能力沉淀时 | Kylo 可直接调用的操作手册 |
| `SOUL.md` | 认知更新时 | 自我定义与物理约束 |

## 原则十：最小改动原则

- 不要在修 bug 时顺手重构
- 不要为假想的未来需求添加抽象
- 一个 PR 解决一个问题
- 如果 artifact/建议的前提不成立，不要盲目采纳

## 原则十一：防御性运维

- 杀进程前必须理解进程树完整结构
- 不在 `sitecustomize.py` 中遗留调试代码

---

## Phase 11.2：API 交互与路由原则（2026-03-09）

### 一、智能体不猜测，先沟通再执行

- 不确定性即提问：用户意图模糊时，优先触发 `ask_user` 澄清，不做主观补全。
- 执行中可互动：任务进行中接收用户补充时，必须即时反馈并支持任务重规划。
- 多消息合并：短时间内连续补充消息应合并到同一任务上下文，而非割裂执行。

### 二、任务驱动模型路由

- 日常任务：`deepseek-v3.2`（chat）主力执行。
- 深度推理任务：`deepseek-r1`（reasoner）用于根因分析、多步规划、复杂设计。
- 轻量判定：`local_think` 用于模糊性检测、复杂度估计、快速摘要。
- 澄清交互：`ask_user` 负责向用户提问并等待回答。

### 三、反馈闭环必须进入 KyloBrain

- 用户澄清与偏好：写入 `preference` 记忆。
- 执行失败与修复尝试：写入 `failure_patterns` 与 `fix_history`。
- 成功链路：记录完整输入→规划→执行→结果，作为后续 few-shot 经验。

### 四、循环控制与人工介入

- 自动修复最多 3 次（`MAX_RETRIES=3`），超过上限必须请求人工介入。
- 失败循环不允许无限重试，不允许同错误模式盲目重复。
- 达到上限后任务状态切换为 `needs_human_intervention`，等待用户决策。

### 五、任务状态可观测

`active_task.json` 必须维护以下字段：
- `clarification_pending`
- `clarification_question`
- `fix_history`

这些字段用于实时观测任务是否在等待澄清、是否进入修复循环、以及每次修复的历史轨迹。
- watchdog 的杀进程逻辑必须考虑 launcher 委托场景
- `start_gateway.bat` 修改后必须实际测试完整启动流程
