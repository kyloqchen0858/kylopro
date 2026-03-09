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

### 飞书失败闭环（新增）
- 外部 API 失败必须写入 `brain/warm/failures.jsonl`
- `pre_task` 在执行前优先检查 `failures`，若命中则给出规避提示
- 同类失败重复出现时优先执行最小验证路径：`status -> get_token -> send_message`

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

飞书场景推荐：
```json
{
  "action": "recall",
  "params": {"query": "feishu create_doc 404", "collection": "failures"}
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

---

## 向量记忆子系统（原 kylo-memory，已整合）

KyloBrain 的三层记忆之外，向量记忆通过 ChromaDB 提供语义检索能力，补充 WARM 层的精确回忆。

### 向量集合（Collection）分类

| 集合名 | 存什么 | 示例 |
|--------|--------|------|
| `preference` | 用户偏好、操作习惯 | "用户喜好竖排代码注释" |
| `decision` | 技术决策与架构选择 | "选择 ChromaDB 而非 Pinecone，因为可本地运行" |
| `project_fact` | 项目事实、配置细节 | "DeepSeek key 在 config.json providers.deepseek" |
| `code` | 可复用代码片段、模式 | "asyncio retry 装饰器实现方式" |

### 向量 CLI 命令（通过 exec 执行）

```bash
# store — 存储一条记忆
python memory/memory_manager.py store --text "内容" --collection preference --tag "tag1,tag2"

# search — 语义检索
python memory/memory_manager.py search --query "检索词" --collection decision --top-k 5

# list — 列出集合全部记忆
python memory/memory_manager.py list --collection project_fact --limit 20

# delete — 按 ID 删除
python memory/memory_manager.py delete --id abc12345
```

### 向量记忆存储时机
- 用户明确说出偏好或习惯 → `preference`
- 做出架构或技术决策时 → `decision`
- 获得项目关键事实（key/配置/路径/约束） → `project_fact`
- 完成可复用代码片段 → `code`

### 向量记忆检索时机
- 新对话第一轮，搜 `project_fact` 恢复项目上下文
- 用户问"你还记得…"时，搜对应集合
- 遇到技术问题时，搜 `code` 和 `decision` 找既往经验

### 向量依赖
```bash
pip install chromadb sentence-transformers
```
