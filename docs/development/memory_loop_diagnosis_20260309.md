# 记忆回路诊断报告
## 2026-03-09 · 审查纠错后的真实状态

> **背景**：初审报告（phase11_overview_20260309.md）错误声称「外部能力从未被操作过」。
> 用户指出飞书和 GitHub 都实际操作过，还有过误删 Python 的事故。
> 这暴露的不是飞书问题——是记忆回路本身的断裂。

---

## 一、事实核查：WARM 里到底有什么

### episodes.jsonl：45 条记录

| 类别 | 条数 | 关键证据 |
|------|:----:|----------|
| feishu:send_message 成功 | 3 | message_id: om_x100b55dc6ae864a, om_x100b55dc1ecf75, om_x100b55d9d7b0ad |
| feishu:create_doc 成功 | 2 | doc_id: BFVBdz73Uop8k3xROwijIwVtpfb, Pc4kdSsgVovSGzxzGq2jYGchppn |
| feishu:create_doc 失败 | 5 | HTTP 404 / 400 invalid param |
| feishu:send_message 失败 | 3 | token 未配置或过期 |
| oauth2:feishu:auto_refresh | 2 | token 刷新成功 |
| COLD 层建立 | 1 | gist_id: b2aed75bd902cd9553ab17057d613472 |
| QQ 通道 hello | 1 | 通过 QQ 频道连接 |
| Telegram 会话 | 多条 | 账户整理、脑体确认、诊断中断 |
| freelance 工作流 | 4 | add/update/log_time/resume_refresh |
| 系统定时周报 | 1 | 14 个任务，成功率 100% |

### patterns.jsonl：7 种任务模式

| 任务类型 | 成功率 | 样本数 |
|----------|:------:|:------:|
| feishu:create_doc | 36.25% | 7 |
| feishu:send_message | 62.5% | 5 |
| coding | 100% | 2 |
| freelance:add | 100% | 1 |
| freelance:update | 100% | 1 |
| freelance:log_time | 100% | 1 |
| freelance:resume_refresh | 100% | 1 |

### failures.jsonl：6 条失败记录

- feishu.doc_api_404 ×3（含 recovery 建议）
- feishu.auth_missing_or_expired ×1
- feishu.generic_failure ×1
- freelance.no_project_data ×1

---

## 二、脑体循环层：打通了吗？

### 写入端 ✅ 正常工作

```
用户消息 → brain_hooks._patched_process_message()
  → 调用原始 _process_message()
  → _auto_record_episode() → WarmMemory.append("episodes", {...})
  → episodes.jsonl ← 45 条

外部操作 → AuthMiddleware._execute_with_auth()
  → 成功/失败后 → WarmMemory.append("episodes", {...})
  → episodes.jsonl ← feishu send/create/refresh 全部记录
  → WarmMemory.upsert_pattern() → patterns.jsonl
  → WarmMemory.record_failure() → failures.jsonl
```

### 读取端 ❌ 未接通主循环

```
用户消息 → brain_hooks._patched_process_message()
  → _build_brain_context() 注入 system prompt
    → HOT: MEMORY.md（0.67KB，5 行摘要）  ← 几乎空
    → bloom: 3 bits / 10000（0.03%）       ← 无效
    → graph: 2 edges（coding→testing→deploy）← 几乎空
    → ❌ 不调 pre_task_intuition()
    → ❌ 不搜索 WARM episodes
    → ❌ 不读 patterns 成功率
    → ❌ 不读 failures recovery 建议

KyloConnector.on_task_start()  ← 有完整 recall 逻辑
  → pre_task_intuition() → find_similar_failure + find_best_pattern + HOT hints
  → algo_check → bloom_warning + workflow_hint
  → prompt_hint_text → 可直接注入的文本
  → ❌ 但 brain_hooks 的主循环从未调用这个方法
```

### 结论：写读断裂

| 环节 | 状态 | 说明 |
|------|:----:|------|
| episode 写入 | ✅ | _auto_record_episode + AuthMiddleware 都在写 |
| pattern 写入 | ✅ | upsert_pattern 有 7 种模式 |
| failure 写入 | ✅ | 6 条失败记录含 recovery |
| WARM→prompt recall | ❌ | _build_brain_context 不搜 WARM |
| pre_task 直觉 | ⚠️ | 代码在，只在显式调 kylobrain 工具时才跑 |
| bloom warning | ⚠️ | post_task_update 会更新 bloom，但主路径不经过 connector |
| pattern graph | ❌ | 只有 2 edges，record_sequence 需手动传 task_sequence |

---

## 三、经验复用（记忆）层：打通了吗？

### HOT（MEMORY.md）→ prompt 注入 ✅ 但内容稀薄

- `_build_brain_context()` 确实读取 HOT 并注入最近 5 行
- 但 MEMORY.md 只有 0.67KB，几乎没有从 WARM 巩固过来的内容
- `daily_consolidation()` cron 存在但数据表明执行效果极有限

### WARM → recall ❌ 未接通

- `WarmMemory.search()` 有 Jaccard + vector 双模式搜索
- `find_similar_failure()` 和 `find_best_pattern()` 代码正确
- 但只有一个入口：`kylobrain(action='pre_task', task='...')`
- Kylo 的主消息循环不自动调用

### COLD（GitHub Gist）→ 回忆 ⚠️ 存在但未验证回读

- gist_id: b2aed75bd902cd9553ab17057d613472 已建立
- 归档功能 `consolidate()` 可以写入
- 但 COLD→WARM 的回忆路径（老记忆搜索）从未测试

### 跨版本迁移 ❌ 断裂

- `_kylopro_publish/memory/HISTORY.md` 记录了误删 Python 事件（litellm+lark_oapi 被清理）
- 这些历史从未迁移到 Kylopro-Nexus 的 WARM 层
- 意味着 Kylo 换了"身体"之后，旧"记忆"没有跟过来

---

## 四、为什么初审会错

### 根因：审查者（新会话）无法看到 Kylo 的运行时记忆

1. 我作为新会话的 Copilot agent，读了代码结构但**没有读 episodes.jsonl**
2. 我从代码的 TODO/设计注释中推断"应该还没跑过"，而实际数据已经存在
3. Kylo 的 WARM 数据在 `brain/warm/*.jsonl` 里，不在常规代码审查路径上
4. `MEMORY.md`（HOT）内容太少（0.67KB），无法从中看到操作历史

**教训**：这恰恰验证了用户的诊断——记忆循环出了问题。不仅 Kylo 自己在运行时无法recall 自己的经验，连审查者回来看也找不到。

---

## 五、修复路径

### 🔴 P0：接通读取端

**文件**：`core/brain_hooks.py`

1. 在 `_build_brain_context()` 中增加 WARM episode 搜索：
```python
# 在 HOT 摘要之后、bloom 之前
try:
    task_text = "最近任务"  # 或从当前会话上下文提取
    recent = conn.brain.warm.read_recent("episodes", days=7)
    if recent:
        ep_lines = [f"- [{e.get('task','')}] → {e.get('outcome','')[:60]}" for e in recent[-5:]]
        parts.append("## 📋 近期操作记忆\n" + "\n".join(ep_lines))
except Exception:
    pass
```

2. 在 `_patched_process_message()` 中调用 `on_task_start()`：
```python
conn = _get_connector()
if conn:
    hints = conn.on_task_start(task_id, task_preview)
    hint_text = hints.get("prompt_hint_text", "")
    # 将 hint_text 注入到本次消息的 context 中
```

### 🟡 P1：修复 bloom filter 接入

- `_auto_record_episode()` 检测到失败时，调用 `conn.algos.bloom.remember_failure(task)`
- 或者让 `_patched_process_message` 里的失败检测分支也走 `on_task_complete(success=False)`

### 🟡 P1：迁移历史记忆

- 将 `_kylopro_publish/memory/HISTORY.md` 中的关键事件转成 WARM episodes
- 特别是误删 Python 事件——这是重要的失败经验

### 🟢 P2：HOT 巩固频率

- 当前 `daily_consolidation()` 效果不明显
- 确认 cron 是否真的在执行
- 可能需要在 WARM→HOT 巩固时提取更多有用信息
