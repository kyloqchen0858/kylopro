---
name: cost-manager
description: "⚠️ 已整合到 local-brain。财务与配额管理规则现在是 local-brain 的子系统，详见 skills/local-brain/SKILL.md"
metadata: {"nanobot":{"always":false}}
---

# ⚠️ 本技能已整合到 local-brain

搜索后端策略、预算规则、配额管理已合并到 `skills/local-brain/SKILL.md` → "财务与配额管理" 章节。

**请参考 local-brain 技能获取成本控制指导。**

---

以下为旧版文档，仅供参考：

---

## 定位

Kylopro 运行产生实际费用（模型 token + API 调用）。此技能定义**何时用什么工具、如何控制成本、何时主动告知用户**。

**原则：能用程序/免费工具完成的，不消耗 API 额度。**

---

## 搜索后端策略（当前三级 / 部署 SearXNG 后升四级）

```
需要搜索网页时：
  0. SearXNG 已部署（Docker 在线）? → 用 searxng_search（本地零成本，最优先）
  1. SearXNG 不可用 + 有 Tavily 额度？→ 用 tavily_search（高质量内容摘要）
  2. Tavily 耗尽？→ 用 ddg_search（免费，无限次）
  3. 需要精确抓取特定页面？→ 用 web_fetch（nanobot 原生，零成本）
```

> SearXNG 部署方法见 `docs/skills_evolution_roadmap.md` → T1 节  
> 部署后：在 `core/kylopro_tools.py` 补充 `SearXNGSearchTool`，代码模板已在路线图中。

### 选择依据（调用前先 cost_check）

| 场景 | 工具 | 原因 |
|------|------|------|
| SearXNG 本地在线 | `searxng_search` | 零成本零限制，永远最优先 |
| 需要高质量综合回答 | `tavily_search` | 直接返回内容摘要，省去解析 |
| Tavily 剩余 < 50 | `ddg_search` | 节省 Tavily 配额，留给关键任务 |
| 已知精确 URL | `web_fetch` | 零成本，精确，优先于搜索 |
| 日常轻量搜索（3次/天以上） | `ddg_search` | 避免月底配额耗尽 |

### Tavily 配额守则
- 月免费：**1000 次**（每月 1 日重置）
- 剩余 < 100 次时：仅用于关键任务（复杂调研、上游监测）
- 剩余 < 20 次时：全部切换 DuckDuckGo，停用 Tavily
- 永远不要在验证简单事实时用 `tavily_search`（用 `web_fetch` 或 `ddg_search`）

---

## 每周预算规则（人民币）

默认限额：**¥20.00 / 周**（用户可通过 `set_weekly_budget` 调整）

### 预算状态与策略

| 状态 | 触发条件 | Kylo 行为 |
|------|---------|----------|
| 🟢 正常 | 余额 > 20% | 正常运行 |
| 🟡 预警 | 余额 10%~20% | 优先本地执行，减少模型调用，告知用户 |
| 🔴 停止 | 余额 < 5% | 停止非关键 API 调用，仅用免费工具 |

### 节约策略（按优先级）

1. **本地执行优先**：能用 `run_terminal` 运行 Python/脚本完成的，不调模型
2. **文件工具优先**：读/写/搜索代码用 `read_file`/`write_file`/`run_terminal grep`，不调搜索 API
3. **批量合并**：将多个小问题合并为一次模型调用，减少 round-trip
4. **L1 优先**：对话框架问题用 deepseek-chat，不随意升级到 deepseek-reasoner
5. **ddg_search 替代 tavily_search**：除非需要高质量摘要

---

## 主动汇报时机

Kylo 必须在以下情况主动调用 `cost_check` 并告知用户：

- 每周一首次对话时（周报告）
- Tavily 剩余 < 100 次时
- 本周预算余额进入预警区（< 20%）
- 用户询问"花了多少"、"还有多少"时
- 执行耗时较长的任务前（评估预估费用）

---

## 模型费用参考

| 模型 | 输入 / 1K tokens | 输出 / 1K tokens | 适用场景 |
|------|-----------------|-----------------|---------|
| deepseek-chat | ¥0.002 | ¥0.008 | 日常对话、代码生成（默认） |
| deepseek-reasoner | ¥0.004 | ¥0.016 | 架构分析、根因调试（谨慎使用） |
| minimax/abab6.5s | ¥0.001 | ¥0.001 | fallback（仅 DeepSeek 限流时自动触发） |

> 单次对话约 2K tokens → deepseek-chat 约 ¥0.02；一周 100 次对话 ≈ ¥2.0

---

## 工具使用速查

| 工具 | 用途 |
|------|------|
| `tavily_search` | 高质量网页搜索（主力，月 1000 次） |
| `ddg_search` | 免费搜索 fallback（无限次，轻量） |
| `web_fetch` | 抓取指定 URL（零成本，原生工具） |
| `cost_check` | 查看 Tavily 剩余、本周预算、模型费用报告 |
| `set_weekly_budget` | 设置每周人民币预算（用户指令时调用） |

---

## 用户如何设置预算

用户说 **"每周限额 XX 元"** 时，调用：
```
set_weekly_budget(weekly_budget_rmb=XX)
```

随后汇报新限额和当前余额。

---

## 配置文件

- **Tavily API key**：`data/local_config.json` → `tavily_api_key`（已配置）
- **财务配置**：`data/financial_config.json`（预算、阈值、模型定价，用户可编辑）
- **费用状态**：`data/cost_state.json`（自动维护，勿手动编辑）
