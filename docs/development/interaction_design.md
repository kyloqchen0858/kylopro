# Kylo 交互层重设计
## 从「单线程执行机器」到「能对话的 AI 助手」

> **日期**：2026-03-09
> **存档**：`docs/development/interaction_design.md`
> **背景**：飞书工作流暴露的根本问题——执行层和对话层完全耦合，交互感几乎为零

---

## 一、当前架构的根本缺陷

### 1.1 现在发生了什么

```
用户发消息
    ↓
AgentLoop 开始处理（同步阻塞）
    ↓
工具调用 1：「让我检查一下目录」
    ↓
工具调用 2：「让我检查一下 Python」
    ↓
工具调用 3：「让我检查一下 nanobot 环境」
    ↓  ← 用户这期间发了「可以中断了」「走通了」
工具调用 4：继续执行，对新消息视而不见
    ↓
最终回复
```

**三个死穴：**

1. **单线程阻塞**：AgentLoop 在跑的时候，新消息进来只能排队，不能被感知
2. **执行过程即对话内容**：「让我检查一下 Python」这种工作日志直接发进对话，污染信道
3. **无意图确认**：模糊指令直接执行，不问清楚，要么走错方向要么做了不需要做的事

### 1.2 助手和对话机器人的本质区别

| | 对话机器人 | 真正的助手 |
|---|---|---|
| 你说一句 | 它回一句 | 它回一句，同时可以继续干活 |
| 你补充一条 | 排队等上一条处理完 | 立刻感知，融合进当前任务 |
| 任务执行中 | 沉默或刷工作日志 | 偶尔同步关键进展，不打扰 |
| 你说「停」 | 等当前工具调用结束才能停 | 立刻响应，graceful stop |

---

## 二、架构设计：两层分离

### 2.1 对话层 + 执行层

```
┌──────────────────────────────────────────────────────┐
│                    用户（Telegram）                    │
└──────────────────┬───────────────────────────────────┘
                   │ 消息流（双向）
┌──────────────────▼───────────────────────────────────┐
│                   对话层（始终在线）                   │
│  · 立即确认收到（< 1 秒）                              │
│  · 意图不清 → 追问，不执行                             │
│  · 多条快速消息 → 合并后理解                           │
│  · 执行中收到新消息 → 判断：打断 / 追加 / 忽略         │
│  · 只说关键信息，不发工作日志                          │
└──────────────────┬───────────────────────────────────┘
                   │ 任务指令（异步）
┌──────────────────▼───────────────────────────────────┐
│                   执行层（后台运行）                   │
│  · TaskBridge 管理任务状态                             │
│  · spawn 子 Agent 处理耗时任务                         │
│  · 进度只在被问时才汇报                                │
│  · 完成 / 失败时主动通知对话层                         │
└──────────────────────────────────────────────────────┘
```

### 2.2 四个具体能力

#### 能力一：意图追问（Intent Clarification）

**触发条件**：
- 动词是「整理」「处理」「搞一下」「帮我看看」等模糊词
- 缺少关键参数（哪个平台？哪个页面？时间范围？）
- 上一次做类似任务失败过（WARM 记录）

**实现**：已在 `brain_hooks.py` 的 `_is_ambiguous_instruction` 和 `_route_task` 中有基础版本，需优化阈值和追问质量。

#### 能力二：消息合并（Message Coalescing）

**设计**：在消息入队时，检测 3 秒窗口内同一用户的连续消息，合并后作为一条处理。

**实现位置**：`core/message_coalescer.py`（待创建）

```python
class MessageCoalescer:
    WINDOW_SEC = 3.0

    def __init__(self):
        self._pending: dict[str, list] = {}
        self._timers: dict[str, float] = {}

    def add(self, user_id: str, message: str) -> str | None:
        now = time.time()
        if user_id not in self._pending:
            self._pending[user_id] = []
        self._pending[user_id].append(message)
        self._timers[user_id] = now
        if now - self._timers[user_id] >= self.WINDOW_SEC:
            return self._flush(user_id)
        return None

    def _flush(self, user_id: str) -> str:
        msgs = self._pending.pop(user_id, [])
        self._timers.pop(user_id, None)
        if len(msgs) == 1:
            return msgs[0]
        return "\n".join(msgs)
```

#### 能力三：执行中打断（Mid-task Preemption）

**设计**：在 `_run_agent_loop` 的工具调用循环中，每次调用后检查信箱。

**实现位置**：`nanobot/agent/loop.py`（需 P1 授权修改 nanobot 核心）

```python
async def _check_preemption(self, user_id: str) -> str | None:
    if self.task_bridge and self.task_bridge.should_stop(user_id):
        return "用户请求中断"
    pending = await self.channel.peek_pending(user_id)
    if pending:
        interrupts = ["停", "stop", "cancel", "中断", "算了", "等等", "先停"]
        if any(kw in pending.lower() for kw in interrupts):
            return f"用户发来打断信号：{pending}"
    return None
```

#### 能力四：执行反馈分离（Execution Feedback Decoupling）

**原则**：
- ✅ 发到对话：「✅ 飞书工作流已走通」「❌ 报错了，原因是 X」
- ❌ 不发到对话：「让我检查一下目录」「让我运行一下 Python」

**实现**：
1. SOUL.md + AGENTS.md 硬规则约束（本次完成）
2. ToolResult 增加 `silent` 字段（Phase 11.5）
3. `on_progress` 回调过滤（Phase 11.5）

---

## 三、实施优先级

### 立刻可做（不改 nanobot 核心）

| 优先级 | 动作 | 文件 | 状态 |
|--------|------|------|------|
| P0 | 「不汇报执行过程」写进 SOUL.md | `SOUL.md` | ✅ Phase 11.3 完成 |
| P0 | AGENTS.md 加交互行为规则 | `AGENTS.md` | ✅ Phase 11.3 完成 |
| P1 | MessageCoalescer 消息合并 | `core/message_coalescer.py` | Phase 11.5 |
| P1 | 行为评分器 | `core/behavior_scorer.py` | Phase 11.5 |

### 下一轮（需要改 nanobot）

| 优先级 | 动作 | 文件 | 状态 |
|--------|------|------|------|
| P2 | Preemption 检查点 | `nanobot/agent/loop.py` | Phase 11.5 |
| P2 | ToolResult silent 字段 | `nanobot/agent/loop.py` | Phase 11.5 |
| P3 | 对话层与执行层完全分离 | 架构重构 | Phase 13+ |

---

## 四、算法和 AI 的关系

算法本身不"思考"，LLM 才思考。算法做的事是在 LLM 的输入和输出上做结构化处理。

### 第一类：输入侧算法（告诉 AI 该怎么想）

```
历史 episodes（WARM）
    ↓ Jaccard / 向量检索  ← 算法：找"最像当前任务"的历史经验
    ↓
相关经验片段
    ↓
注入到 system prompt："上次类似任务你这样做失败了，注意避免 X"
    ↓
LLM 调用
```

**Kylo 现状**：BrainHooks 已在做这件事，但检索内容质量低（WARM 里缺真实操作数据）。

### 第二类：输出侧算法（评价 AI 做得怎么样）

```
LLM 输出 + 工具执行结果
    ↓
规则评分算法（不调 LLM，纯逻辑）：
    · 任务完成了吗？→ success_rate 更新
    · 用了几轮工具调用？→ efficiency_score
    · 用户有没有打断？→ interruption_flag
    · 花了多少钱/时间？→ cost_score
    ↓
写入 WARM patterns
```

**Kylo 现状**：只在 auth_middleware 和 freelance 中有评分，主循环未接入。

### 第三类：调度算法（决定用哪个 AI、怎么用）

```
收到任务
    ↓
复杂度估算：关键词匹配 + 历史相似任务平均耗时
    ↓
路由：简单 → L0 / 中等 → L1 / 复杂 → L2 / 模糊 → 先追问
```

**Kylo 现状**：唯一真正在闭环运行的算法。

### 行为设计和算法的闭环

```
设计一个行为（比如：意图模糊时追问）
    ↓
Kylo 执行了这个行为
    ↓
算法记录：追问了吗？追问后成功率提升了吗？
    ↓
数据积累够 10 次后 → 算法结论 → 写进 WARM patterns
    ↓
下次自动提权这个行为的优先级
```

**当前缺口**：行为发生了，但算法没在记录它，永远不会形成闭环。需要 `behavior_scorer.py` 来闭合这个环。

---

## 五、安全设计

### 四层防御

1. **账户隔离**：AI 专用最小权限账户
2. **操作分级**：只读/写入/破坏性三级
3. **输入净化**：外部内容标记 `[EXTERNAL_CONTENT]`
4. **审计日志**：每次工具调用记录到 `data/action_log.jsonl`

详细设计见 `AGENTS.md` 安全加固规则章节。
