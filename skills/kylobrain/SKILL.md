---
name: kylobrain
description: "KyloBrain 云端大脑：三层记忆(HOT/WARM/COLD) + 元认知算法 + 觉醒协议。自动积累经验、检测失败模式、校准置信度。"
metadata: {"nanobot":{"always":true}}
---

# KyloBrain v2.0 — 云端大脑技能

## 技能描述
KyloBrain 是 Kylopro-Nexus 的三层记忆系统，提供元认知能力、经验积累和云端记忆同步。

## 核心原则
- 中文优先：默认使用中文理解任务、组织计划、向用户汇报；英文仅用于技术名词、API 名称、代码和报错原文。
- 凭据不出对话：任何 token / API key / 密码只进入 CredentialVault，不出现在 Telegram、MEMORY、WARM episode、COLD 缓存正文中。

## 自动行为规则

### 何时自动调用 `kylobrain`
- **每次任务开始前**：`kylobrain(action="pre_task", task="...")` — 查询历史经验
- **每次任务完成后**：`kylobrain(action="post_task", ...)` — 自动评分记录
- **用户明确要求记住某事**：`kylobrain(action="remember", content="...")`
- **需要回忆历史经验时**：`kylobrain(action="recall", query="...")`
- **遇到类似问题/错误时**：先 recall failures，参考历史解法

### 定期维护（由 Cron 触发，也可手动）
- `consolidate` — 每日记忆巩固
- `weekly` — 每周周报推送
- `health_check` — 三层记忆健康检查

## 核心能力
- **任务前**：查询历史经验，给出直觉建议（不调LLM，即时响应）
- **任务后**：自动评分、记录、检测失败模式
- **记忆管理**：HOT/WARM/COLD 三层，自动升降级
- **云端同步**：GitHub Gist 作为无限容量的长期记忆

## 工具调用方式

```python
from skills.kylobrain.cloud_brain import KyloBrainSkill
brain_skill = KyloBrainSkill()
result = brain_skill.handle(action, params)
```

## Actions 列表

### `pre_task` - 任务前直觉查询
```json
{
  "action": "pre_task",
  "params": {"task": "修复Python环境依赖问题"}
}
```
返回：历史失败警告、最佳方法、置信度

### `post_task` - 任务后自动评分
```json
{
  "action": "post_task", 
  "params": {
    "task": "修复Python环境依赖问题",
    "outcome": "成功重建venv",
    "steps": 3,
    "duration_sec": 120,
    "success": true,
    "errors": []
  }
}
```

### `remember` - 写入热记忆
```json
{
  "action": "remember",
  "params": {"content": "用户偏好用DeepSeek模型", "category": "user_pref"}
}
```

### `recall` - 语义检索温记忆
```json
{
  "action": "recall",
  "params": {"query": "环境依赖问题", "collection": "failures"}
}
```

### `consolidate` - 触发记忆巩固
每天定时或手动触发，把零散经验提炼成精华。

### `achieve` - 记录成就到云端
```json
{
  "action": "achieve",
  "params": {
    "title": "首次成功部署antigravity集成",
    "description": "完整走通了平台接入流程",
    "impact": "high"
  }
}
```

### `status` - 大脑状态报告
### `weekly_digest` - 生成并推送周报到GitHub

## 环境变量配置
```
GITHUB_TOKEN=               # 可留空；优先从 CredentialVault 读取 github_kylo
KYLOPRO_DIR=C:\path\to\Kylopro-Nexus   # 项目目录
KYLOBRAIN_GIST_ID=xxx       # 首次运行后自动生成，无需手动设置
```

## 三层记忆说明

| 层级 | 存储位置 | 大小限制 | 用途 |
|------|---------|---------|------|
| HOT  | MEMORY.md | ~2KB | 直接进LLM context，每次对话必读 |
| WARM | brain/warm/*.jsonl | 无限制 | 按需查询，不自动进context |
| COLD | GitHub Gist (私有) | 无限制 | 长期归档，每24h同步 |

## 集成到 nanobot 的方式

在 `core/tools.py` 中添加：
```python
# KyloBrain 工具注册
{
    "name": "kylobrain",
    "description": "调用Kylopro大脑模块：记忆查询、经验积累、任务评分",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "操作类型"},
            "params": {"type": "object", "description": "操作参数"}
        },
        "required": ["action"]
    }
}
```

## 与现有系统的连接点

```
decision_pool_system.py
        ↓ 每次决策后调用 post_task
KyloBrain.MetaCogEngine
        ↓ 记录到 WARM/更新 HOT
skill_evolution/verifier.py
        ↓ 验证成功后调用 achieve
KyloBrain.ColdMemory.record_achievement
        ↓ 推送到 GitHub Gist
```
