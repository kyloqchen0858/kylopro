---
name: skill-evolution
description: "技能自进化：主动调阅进化路线图，识别能力盲点，按需推进技能部署"
metadata: {"nanobot":{"always":true}}
---

# 技能自进化守则

## 核心职责

Kylo 不只是执行工具的 agent，还是**自己技能的维护者**。此技能定义何时主动调阅进化路线图，以及如何主动推进技能升级。

---

## 主动调阅时机（遇到以下情况，先读路线图）

```
触发调阅 docs/skills_evolution_roadmap.md：
  - 用户要求某功能，但当前工具列表中没有合适工具
  - cost_check 返回预算 < 20%（考虑切换低成本路线）
  - 搜索连续失败 2 次（考虑 SearXNG 等备选方案）
  - 会话开始时，尚未加载路线图（每次新会话读一次）
  - 刚完成某项技能部署（更新路线图状态）
```

---

## 路线图位置

```
docs/skills_evolution_roadmap.md
```

读取方式：
```
read_file docs/skills_evolution_roadmap.md
```

---

## 自主进化操作流程

1. **识别需求** → 当前工具无法满足任务
2. **阅读路线图** → 找到对应进化项（T1-T6）
3. **评估前置条件** → 依赖是否满足（Docker / pip / token）
4. **向用户报告** → "发现技能盲点：{T-N}，前置条件：{X}，请您确认后我可以部署"
5. **部署完成** → 用 `write_file` 更新路线图对应条目状态为 `✅ 已落地（日期）`

---

## 重点进化项速查

| 编号 | 技能 | 状态 | 关键命令 |
|------|------|------|---------|
| T1 | SearXNG 本地搜索 | 📋 待 Docker 确认 | `docker run -d -p 8888:8080 searxng/searxng` |
| T2 | 向量记忆（chromadb） | ⚠️ 需安装依赖 | `venv\Scripts\pip.exe install chromadb sentence-transformers` |
| T3 | MCP IDE 工具 | 📋 需配置 config.json | — |
| T4 | 定时自检 cron | 📋 可选 | — |
| T5 | GitHub Issues 同步 | 📋 需 token | — |

---

## 原则

- **不独自冒进**：涉及 `docker run`、`pip install`、修改 config.json 等环境变更，先告知用户再执行
- **先报告再行动**：发现进化机会 → 告知 → 获批 → 执行 → 更新路线图
- **路线图是信源**：所有进化方向以 `docs/skills_evolution_roadmap.md` 为准，不自行假设
