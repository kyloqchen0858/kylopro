# Memory Identity System — 设计文档
> 来源：Qchen 提供的设计方案
> 整合：Second Me HMM 概念 + Kylo 实际运行场景
> 实现时间：Phase 11.5

---

## 核心思路

将 Kylo 和用户的每次对话数据转化为有意义的自我认知，实现：

```
L0 (原始事件) → L1 (行为模式) → L2 (身份认知)
```

类似 Second Me 的 Hierarchical Memory Modeling (HMM)：
- L0 = Raw Events（每次对话/任务的结构化记录）
- L1 = Behavioral Patterns（纯统计提炼，不用 LLM）
- L2 = Identity Synthesis（LLM 驱动的自我认知生成）

---

## L0 · 原始事件层

### 数据结构

```json
{
  "id": "ep_20260315_001",
  "timestamp": "2026-03-15T10:30:00",
  "source": "telegram",
  "task_type": "feishu_workflow",
  "task_summary": "创建飞书文档并发送通知",
  
  "execution": {
    "success": true,
    "duration_sec": 12.3,
    "tool_calls_count": 4,
    "interrupted_by_user": false,
    "asked_clarification": false
  },
  
  "interaction_quality": {
    "user_feedback_tone": "positive",
    "outcome_summary": "文档创建成功，用户确认收到"
  },
  
  "signal_flags": {
    "is_growth_signal": false,
    "signal_type": null,
    "signal_strength": 0.0
  },
  
  "route": "deepseek-v3.2"
}
```

### 存储
- 路径：`data/memory/L0_episodes/{YYYY-MM-DD}/ep_{NNN}.json`
- 写入时机：每次任务完成后，由 `brain_hooks._auto_record_episode()` 自动调用
- 来源：同时也写入 WARM 层保持向后兼容

---

## L1 · 行为模式层

### 提炼逻辑

**纯统计，不调 LLM**。最低证据数: 5 条。

#### 行为模式 (`behavioral.json`)
- 按 `task_type` 分组
- 计算：success_rate, avg_duration, avg_tool_calls, clarification_rate
- 追问与成功率的相关性 (clarification_lift)
- 自动生成推荐行为

#### 关系模式 (`relational.json`)
- 用户打断率
- 用户反馈情绪分布（positive / neutral / negative）
- 反馈 → 任务结果的相关性

#### 能力域 (`domain.json`)
- 成熟度评估：stable / developing / learning / struggling
- 基于 success_rate + episode_count

### 触发条件
- 同类 episode 积累 10+ 条
- 或每周 cron 任务

---

## L2 · 身份认知层

### 合成流程

```
读取 L1 patterns → 构建 prompt → 调用 deepseek-chat → 生成:
  1. identity_statement.md (自我叙述)
  2. personality dimension 调整提案
     → AuthenticityChecker 检验
       → Qchen 审批
         → 写入 personality_state.json
```

### AuthenticityChecker 规则
1. **Hard floors**: directness ≥ 0.70, autonomy = 1.00
2. **单次变化幅度**: ≤ 0.15
3. **证据充分性**: 不能只靠社交反馈
4. **Qchen 信号**: 至少需要一条来自 Qchen 的反馈作为证据

### 版本管理
- 每次变更创建快照：`data/memory/L2_identity/versions/v{N}_{date}/`
- 触发：personality_update_approved / monthly_scheduled / manual_request
- 支持版本对比和回滚

---

## 实现清单

| 模块 | 路径 | 状态 |
|------|------|------|
| L0 Writer | `core/memory/l0_writer.py` | ✅ 已完成 |
| L1 Extractor | `core/memory/l1_extractor.py` | ✅ 已完成 |
| L2 Synthesizer | `core/memory/l2_synthesizer.py` | ✅ 已完成 |
| Authenticity Checker | `core/memory/authenticity_checker.py` | ✅ 已完成 |
| Version Manager | `core/memory/version_manager.py` | ✅ 已完成 |
| brain_hooks L0 集成 | `core/brain_hooks.py` | ✅ auto_record 已接入 |
| SOUL.md 升级到 v5.0 | `SOUL.md` | ✅ 已更新 |

---

## 数据流向

```
用户对话
  ↓
brain_hooks._auto_record_episode()
  ├── WARM 层 episodes.jsonl（向后兼容）
  └── L0 结构化事件 (data/memory/L0_episodes/)
        ↓
L1Extractor.run()  [cron 或手动触发]
  └── behavioral.json, relational.json, domain.json
        ↓
L2Synthesizer.synthesize()  [L1 完成后或手动触发]
  ├── identity_statement.md (自我叙述)
  └── pending_proposal.json (性格调整提案)
        ↓
AuthenticityChecker.validate_and_update_proposal()
  ├── 通过 → 等待 Qchen 审批
  └── 不通过 → 标记为 blocked
        ↓
Qchen 审批 → L2Synthesizer.apply_approved_changes()
  └── personality_state.json 更新
        ↓
brain_hooks._build_brain_context() 读取并注入系统 prompt
```

---

## 操作指南

### 方式一：手动触发（开发/调试用）

在 Kylopro-Nexus 目录下用 Python 执行：

```python
# Step 1: 迁移 WARM 历史数据到 L0（首次或补充）
from core.memory.l0_writer import migrate_warm_to_l0
migrate_warm_to_l0()

# Step 2: 运行 L1 提炼（纯统计，秒级完成）
from core.memory.l1_extractor import L1Extractor
extractor = L1Extractor()
result = extractor.run()   # 返回 {"behavioral": {...}, "relational": {...}, "domain": {...}}
print(f"L1 complete: {len(result.get('behavioral', {}))} behavioral patterns")

# Step 3: 运行 L2 合成（调用 LLM，约 10-30 秒）
from core.memory.l2_synthesizer import L2Synthesizer
synth = L2Synthesizer()
proposal = synth.synthesize()  # 生成 identity_statement.md + pending_proposal.json
print(f"L2 proposal status: {proposal.get('status')}")

# Step 4: 检查提案（如果有性格调整提案）
from core.memory.authenticity_checker import AuthenticityChecker
checker = AuthenticityChecker()
validation = checker.validate_and_update_proposal()
print(f"Validation: {validation}")

# Step 5: 审批提案（Qchen 确认后执行）
synth.apply_approved_changes()
```

### 方式二：通过 Telegram 命令（推荐日常使用）

让 Kylo 自己执行（发 Telegram 消息）：
- `kylo 跑一下记忆提炼` → Kylo 调用 brain tool 执行 L1+L2
- `kylo 看看你的性格提案` → 查看 pending_proposal.json
- `批准` / `否决` → Qchen 审批

### 方式三：Cron 自动调度（生产推荐）

需在 `~/.nanobot/config.json` 的 cron 段添加定时任务。

#### 配置示例

在 Kylopro-Nexus 的 cron 配置中添加（或通过 `nanobot cron add`）：

```json
{
  "cron": {
    "jobs": [
      {
        "name": "l1_weekly_extraction",
        "schedule": "0 3 * * 0",
        "command": "执行 L1 记忆提炼：运行 core/memory/l1_extractor.py 的 L1Extractor().run()，输出统计 patterns",
        "enabled": true
      },
      {
        "name": "l2_monthly_synthesis",
        "schedule": "0 4 1 * *",
        "command": "执行 L2 身份合成：运行 core/memory/l2_synthesizer.py 的 L2Synthesizer().synthesize()，生成自我叙述，提案等审批",
        "enabled": true
      },
      {
        "name": "warm_to_l0_daily",
        "schedule": "0 2 * * *",
        "command": "迁移 WARM 到 L0：运行 core/memory/l0_writer.py 的 migrate_warm_to_l0()，补充结构化事件",
        "enabled": true
      }
    ]
  }
}
```

> **注意**：nanobot 的 cron 命令是自然语言，Kylo 会解析并执行对应的工具调用。
> 上述 schedule 用标准 cron 表达式：`0 3 * * 0` = 每周日凌晨 3 点。

#### 推荐调度频率

| 操作 | 频率 | 原因 |
|------|------|------|
| WARM→L0 迁移 | 每天凌晨 2 点 | 保证 L0 数据完整 |
| L1 提炼 | 每周日凌晨 3 点 | 积累足够 episodes （MIN_EVIDENCE=5） |
| L2 合成 | 每月 1 号凌晨 4 点 | 需要稳定的 L1 patterns 作为输入 |

#### 目前状态

- WARM→L0：已通过 `brain_hooks._auto_record_episode()` 实时写入（每次对话自动同时写 WARM + L0）
- L1/L2：**尚未配置 cron**，当前需手动或通过 Telegram 命令触发
- 首次运行建议：先手动执行一次完整链路（Step 1-5），确认数据正确后再配 cron
