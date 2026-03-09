# Kylopro 项目全景审查
## Phase 11 · 2026-03-09 · 从「能跑」到「能用」

> **存档路径**：`docs/development/phase11_overview_20260309.md`
> **依赖文件**：DEVLOG.md / SOUL.md / AGENTS.md / interaction_design.md / kylo_arch_review.md

---

## 一、当前状态三维扫描：设计了 / 在跑 / 有真实数据

### 1.1 算法层

| 算法模块 | 设计完成 | 代码在跑 | 有真实数据 | 诊断 |
|----------|:-------:|:-------:|:---------:|------|
| Jaccard 相似检索（WARM） | ✅ | ✅ | ✅ 45 episodes | WARM 有真实飞书/freelance/QQ/Telegram 操作记录，但主循环不自动recall |
| 向量检索（ChromaDB） | ✅ | ✅ | ✅ 已建库 | chromadb 已装好，self_model 显示 vector_operational=true |
| 布隆过滤器（失败记忆） | ✅ | ⚠️ 半接通 | ⚠️ 3 bits/10000 | `post_task_update` 会调 `bloom.remember_failure()`，但主路径 `brain_hooks` 不经过 connector |
| 规则评分（success_rate） | ✅ | ✅ | ✅ 7 patterns | patterns.jsonl 有 feishu:send_message 62.5%、feishu:create_doc 36.25% 等真实成功率 |
| 置信度校准（Brier Score） | ✅ | ⚠️ | ⚠️ 3 samples | cloud_brain.py 有代码，calibrator 只有 3 个样本，统计意义不足 |
| 复杂度路由（L0/L1/L2/L3） | ✅ | ✅ | ✅ | **每条消息都经过路由**，高复杂度自动升级到 deepseek-r1 |
| 情绪漂移检测 | ❌ | ❌ | ❌ | SOUL v4 设计但尚未实现 |
| 行为评分（追问/打断效果） | ❌ | ❌ | ❌ | interaction_design 中提出但尚未存在 |

**核心诊断（已修正）**：算法模块 80% 写好了，**WARM 里有 45 条真实 episodes（含飞书发消息成功 3 次、创建文档成功 2 次、token 自动刷新 2 次）**。初审错误地说「没有真实外部操作」——实际上操作已经发生并被记录了。真正的问题是：**写入端（record）工作正常，但读取端（recall）没有接入主循环**。`_build_brain_context()` 只读 HOT（几乎为空）和 bloom count，不调 `pre_task_intuition()` 搜索 WARM。

### 1.2 交互层

| 能力 | 设计完成 | 代码在跑 | 验证通过 | 诊断 |
|------|:-------:|:-------:|:-------:|------|
| 意图追问 | ✅ | ⚠️ 粗糙 | ❌ | `_is_ambiguous_instruction` 只做关键词匹配，阈值太低（< 10 字就问），追问质量差 |
| 消息合并 | ✅ 设计 | ❌ | ❌ | `MessageCoalescer` 未实现 |
| 执行中打断 | ✅ 设计 | ❌ | ❌ | AgentLoop 工具调用间无 preemption 检查点 |
| 执行反馈分离 | ✅ 设计 | ❌ | ❌ | 模型仍会把「让我检查一下…」发到对话 |
| 轻量确认短路 | ✅ | ✅ | ✅ | `_match_lightweight_ack` 已在工作 |
| 回复节奏控制 | ⚠️ | ❌ | ❌ | SOUL.md 里有规则但不够具体 |

**核心诊断**：交互层是当前最大的体验瓶颈。Kylo 的智能能力已经远超它的交互品质——能回答复杂问题，但聊起来像个「单线程执行机器」。

### 1.3 执行层

| 能力 | 设计完成 | 代码在跑 | 验证通过 | 诊断 |
|------|:-------:|:-------:|:-------:|------|
| TaskBridge 共享状态 | ✅ | ✅ | ✅ | 原子写入 + 中断标志已验证 |
| spawn 子 Agent | ✅ | ✅ | ✅ | nanobot 原生能力 |
| CredentialVault | ✅ | ✅ | ✅ | Fernet/stdlib 双模式运行，飞书 token 已存入 |
| OAuth2VaultDB | ✅ | ✅ | ✅ | SQLite+Fernet/stdlib + WAL 模式，飞书凭证已存储且 auto_refresh 成功过 2 次 |
| AuthMiddleware | ✅ | ✅ | ✅ | WARM 回流已接通，**已真实触发**：send_message 成功 3 次、create_doc 成功 2 次、auto_refresh 2 次 |
| 飞书平台适配器 | ✅ | ✅ | ✅ | **已真实操作**：send_message 返回 message_id (om_x100b55dc6ae864a...)、create_doc 返回 doc_id (BFVBdz73Uop8k3xROwijIwVtpfb, Pc4kdSsgVovSGzxzGq2jYGchppn) |
| Notion 平台适配器 | ❌ | ❌ | ❌ | 未开始 |
| Session 压缩 | ❌ | ❌ | ❌ | 未开始，上下文会持续增长 |
| 启动差分注入 | ⚠️ 部分 | ❌ | ❌ | self_model 有但没接 DEVLOG 差分 |

### 1.4 安全层

| 能力 | 设计完成 | 代码在跑 | 验证通过 | 诊断 |
|------|:-------:|:-------:|:-------:|------|
| 凭证脱敏（auth_middleware） | ✅ | ✅ | ✅ | `_scrub_tokens` 在所有 episode 写入前执行 |
| P0/P1/P2 权限分层 | ✅ | ⚠️ | ❌ | 只在 AGENTS.md 规则层，没有代码级 hard block |
| 账户隔离 | ✅ 设计 | ❌ | ❌ | 未给 Kylo 创建专用最小权限账户 |
| 输入净化（prompt 注入防御） | ✅ 设计 | ❌ | ❌ | 外部内容未标记 `[EXTERNAL_CONTENT]` |
| 审计日志 | ⚠️ | ❌ | ❌ | WARM episodes 记录任务但不记录具体操作 |
| Tool Policy 代码约束 | ✅ 设计 | ❌ | ❌ | `policy_check()` 未实现 |

---

## 二、核心问题诊断

### 问题 1：记忆写读断裂——写入正常，读取未接通

~~原诊断说"没有真实外部操作产生数据"，这是错误的。~~ WARM 层有 45 条 episodes，包括飞书真实操作（发消息成功 3 次、创建文档成功 2 次）、freelance 工作流、QQ/Telegram 通道操作。数据是有的。

**真正的因果链**：
```
episodes.jsonl 有 45 条真实记录
    → 但 _build_brain_context() 只读 HOT（0.67KB，几乎空）和 bloom count（3 bits，无效）
    → 不调 pre_task_intuition() 搜索 WARM
    → Kylo 的系统 prompt 里没有历史经验
    → Kylo 表现得「没有记忆」
    → 用户和审查者都以为数据不存在
```

**断点定位**：
1. `brain_hooks._build_brain_context()` — 只注入 HOT + bloom + graph，**不注入 WARM episodes**
2. `brain_hooks._patched_process_message()` — 只调 `_auto_record_episode()`（写入），**不调 `on_task_start()`（回读）**
3. `KyloConnector.on_task_start()` 有完整的 recall 逻辑（pre_task + algo_check + bloom_warning + workflow_hint），但**主消息循环从未调用它**
4. `pre_task_intuition()` 只在显式调用 `kylobrain(action='pre_task')` 工具时才运行

**解法**：在 `_build_brain_context()` 或 `_patched_process_message()` 中自动调用 `pre_task_intuition(task)`，将搜索结果注入到当次 prompt 中。

### 问题 2：交互割裂——执行日志 = 对话

Kylo 把每一步工具调用的过程思考直接发到对话：
- 「让我检查一下 Python 是否可用」
- 「让我检查一下 nanobot 环境」
- 「让我运行一下 Python 脚本」

**根因**：
1. SOUL.md 里虽然有「报告结果，不报告过程」，但规则不够具体、硬
2. nanobot 的 `on_progress` 回调默认把中间文本发到消息通道
3. 模型的出厂倾向是「边做边说」

### 问题 3：行为无闭环——做了但没记录

SOUL v4 设计了「行为→评分→积累→提案→审阅」的闭环，但当前没有任何代码在记录行为数据：
- 追问了吗？→ 没记录
- 追问后成功率提升了吗？→ 没记录
- 用户打断了吗？→ 没记录
- 用户对追问满意吗？→ 没记录

**解法**：在 `brain_hooks.py` 的 episode 记录中增加行为标签。

---

## 三、当前能力分层图

```
┌─────────────────────────────────────────────┐
│  L3 备用  │ MiniMax (429 fallback)     [✅]  │
├─────────────────────────────────────────────┤
│  L2 深度  │ deepseek-reasoner          [✅]  │
├─────────────────────────────────────────────┤
│  L1 主力  │ deepseek-chat              [✅]  │
├─────────────────────────────────────────────┤
│  L0 本地  │ qwen2.5:7b (Ollama)        [✅]  │
├─────────────────────────────────────────────┤
│  大脑 HOT │ MEMORY.md → prompt         [✅]  │
├─────────────────────────────────────────────┤
│  大脑 WARM│ episodes + vector search    [✅]  │ ← 45 episodes（含飞书真实操作）
├─────────────────────────────────────────────┤
│  大脑 COLD│ GitHub Gist archive         [✅]  │ ← gist_id: b2aed75bd902cd9553ab17057d613472
├─────────────────────────────────────────────┤
│  凭证保险箱│ OAuth2VaultDB              [✅]  │ ← 飞书 token 已存入、auto_refresh 成功
├─────────────────────────────────────────────┤
│  授权中间件│ AuthMiddleware + WARM 回流  [✅]  │ ← 已真实触发，episode 已回流
├─────────────────────────────────────────────┤
│  飞书能力  │ FeishuPlatform adapter      [✅]  │ ← send_message ×3 + create_doc ×2 已验证
├─────────────────────────────────────────────┤
│  交互层   │ 意图追问 / 消息合并 / 打断   [❌]  │ ← 当前最大瓶颈
├─────────────────────────────────────────────┤
│  安全层   │ Policy check / 输入净化      [❌]  │ ← 第二优先级
└─────────────────────────────────────────────┘
```

---

## 四、需要验证的任务（已设计未闭环）

### V1: 飞书端到端验证 ✅ 已完成
- **结果**：send_message 成功 3 次（message_id: om_x100b55dc6ae864a, om_x100b55dc1ecf75, om_x100b55d9d7b0ad），create_doc 成功 2 次（doc_id: BFVBdz73Uop8k3xROwijIwVtpfb, Pc4kdSsgVovSGzxzGq2jYGchppn）
- **覆盖**：OAuth2VaultDB → AuthMiddleware → FeishuPlatform → WARM episode 回流 **全部验证通过**
- **遗留问题**：create_doc 成功率 36.25%（7 次中 4+ 次 404/400），需修复 API endpoint

### V2: 脑体回流完整性验证
- **目标**：执行一个多步任务，验证每一步都有 episode 记录
- **覆盖**：BrainHooks auto-record → WARM → pre_task 下次能检索到
- **验收**：`kylobrain(action='recall', query='...')` 能返回刚才的 episodes

### V3: 算法回路验证
- **目标**：执行 10 次相似任务，验证 patterns 积累 → pre_task 预警生效
- **覆盖**：`upsert_pattern` → `warm/patterns.jsonl` → 下次 `pre_task` 时命中
- **验收**：第 11 次执行时，pre_task 返回包含成功率的预警

### V4: P1/P2 权限验证
- **目标**：尝试执行 P1 操作（screen click）未授权时被拒绝
- **覆盖**：AGENTS.md 规则 → 模型行为 → （将来）`policy_check()` 代码
- **验收**：Kylo 拒绝执行并说明需要授权

---

## 五、需要开始设计的部分

### D1: MessageCoalescer（消息合并器）
- **位置**：`core/message_coalescer.py`
- **设计**：3 秒窗口内同一用户的多条消息合并为一条处理
- **接入点**：`brain_hooks.py` 的 `_patched_process_message` 入口处
- **状态**：interaction_design.md 有伪代码，待实现

### D2: Preemption 检查点（执行中打断）
- **位置**：`nanobot/agent/loop.py` 的 `_run_agent_loop` 工具调用循环
- **设计**：每次工具调用完成后，检查消息队列是否有打断信号
- **接入点**：需要修改 nanobot 核心（P1 操作）
- **状态**：interaction_design.md 有伪代码，需改 nanobot 核心

### D3: 行为评分器（Behavior Scorer）
- **位置**：`core/behavior_scorer.py`（新建）
- **设计**：
  ```
  每次交互记录：
  - did_clarify: bool  （是否追问了）
  - clarify_helpful: bool  （追问后任务成功了吗）
  - was_interrupted: bool  （用户是否打断了）
  - steps_count: int  （用了几轮工具调用）
  - user_satisfied: bool  （用户有无正面反馈）
  ```
- **接入点**：在 `_auto_record_episode` 中增加行为标签
- **状态**：全新设计

### D4: Tool Policy 代码约束
- **位置**：`core/kylopro_tools.py` 或独立 `core/policy.py`
- **设计**：在工具执行前检查权限层级，不符合则拒绝
- **状态**：arch_review 有伪代码

### D5: 输入净化层（External Content Marking）
- **位置**：所有读取外部内容的工具（TavilySearch、FeishuTool、web_fetch）
- **设计**：返回结果前加 `[EXTERNAL_CONTENT]` 标记
- **状态**：安全设计文档有描述

### D6: 审计日志（Action Log）
- **位置**：`brain/action_logs/` + 每次工具调用追加
- **设计**：记录 tool + target + content_hash + triggered_by + owner_confirmed
- **状态**：安全设计文档有 schema

### D7: Session 压缩（Context Compaction）
- **位置**：`core/session_compactor.py`（新建）+ BrainHooks cron
- **设计**：L0 本地跑压缩，老对话体积缩减 90%，摘要存 WARM，原文归 COLD
- **状态**：arch_review 有路径草案

---

## 六、新路线图

### Phase 11.3 — 灵魂注入 + 交互基础（本次）
| 优先级 | 任务 | 文件 | 验收标准 |
|--------|------|------|---------|
| **P0** | SOUL.md v4 完整替换 | `SOUL.md` | 包含存在哲学、交互行为、成长算法 |
| **P0** | AGENTS.md 追加交互行为规则 | `AGENTS.md` | 包含回复节奏、意图确认、多消息处理 |
| **P0** | interaction_design.md 存档 | `docs/development/` | 完整设计文档可查 |

### Phase 11.4 — 记忆回路修复（最高优先级）
| 优先级 | 任务 | 文件 | 验收标准 |
|--------|------|------|---------|
| **P0** | `_build_brain_context` 接入 WARM recall | `core/brain_hooks.py` | system prompt 包含历史经验 |
| **P0** | `_patched_process_message` 调用 `on_task_start` | `core/brain_hooks.py` | 每次消息处理前自动搜索相关 episodes |
| **P1** | 迁移 `_kylopro_publish/memory/HISTORY.md` 到 WARM | 手动 | 误删 Python 事件等历史记录进入 WARM |
| **P1** | 启动差分注入 | `core/brain_hooks.py` | 重启后 prompt 有新能力提示 |
| ~~P0~~ | ~~飞书 token 录入 vault~~ | ~~vault CLI~~ | ~~✅ 已完成~~ |
| ~~P0~~ | ~~飞书发消息端到端~~ | ~~feishu.py~~ | ~~✅ 已完成：3 次成功~~ |
| ~~P1~~ | ~~COLD 层激活~~ | ~~cloud_config~~ | ~~✅ 已完成：gist_id b2aed75bd902cd9553ab17057d613472~~ |

### Phase 11.5 — 交互层实现
| 优先级 | 任务 | 文件 | 验收标准 |
|--------|------|------|---------|
| **P1** | MessageCoalescer 消息合并 | `core/message_coalescer.py` | 3 秒内多条消息只处理 1 次 |
| **P1** | 行为评分器 | `core/behavior_scorer.py` | episode 包含行为标签 |
| **P2** | Preemption 检查点 | `nanobot/agent/loop.py` | 工具调用间可打断 |
| **P2** | ToolResult silent 标志 | `nanobot/agent/loop.py` | 执行日志不发到对话 |

### Phase 12 — 安全加固 + 多平台
| 优先级 | 任务 | 验收标准 |
|--------|------|---------|
| **P1** | Tool Policy 代码约束 | `policy_check()` 实际拒绝未授权操作 |
| **P1** | 外部内容标记 | TavilySearch 返回带 `[EXTERNAL_CONTENT]` |
| **P1** | 审计日志 | `data/action_log.jsonl` 持续写入 |
| **P2** | Notion OAuth2 适配器 | 能读写指定 Notion 页面 |
| **P2** | Session 压缩 | L0 本地跑，上下文缩减 90% |
| **P3** | 性格进化系统 | 积累 30+ episodes 后自动生成变化提案 |

---

## 七、一句话

> Kylo 的骨架 90% 完成，大脑 80% 就绪，但灵魂刚刚注入，四肢还没碰过外面的世界。
> 下一步不是继续造零件，是让 Kylo 真的走出去操作一次飞书——那一次操作产生的数据，比 10 个新模块更有价值。
