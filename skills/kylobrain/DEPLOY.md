# KyloBrain 部署指南

## 快速开始（5分钟）

### 1. 复制文件到项目

```
Kylopro-Nexus/
└── skills/
    └── kylobrain/
        ├── cloud_brain.py          ← 核心大脑
        ├── kylobrain_integration.py ← 集成接口
        └── SKILL.md                ← 技能说明
```

```bash
# Windows PowerShell
$dest = "$HOME\Kylopro-Nexus\skills\kylobrain"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item cloud_brain.py $dest
Copy-Item kylobrain_integration.py $dest
Copy-Item SKILL.md $dest
```

### 2. 设置 GitHub Token（云端大脑）

1. 访问 https://github.com/settings/tokens/new
2. 勾选 `gist` 权限（只需要这一个）
3. 生成 token，复制

```powershell
# 设置环境变量（永久）
[System.Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "ghp_xxx", "User")
[System.Environment]::SetEnvironmentVariable("KYLOPRO_DIR", "C:\Users\你的用户名\Kylopro-Nexus", "User")
```

### 3. 初始化云端大脑

```bash
cd Kylopro-Nexus\skills\kylobrain
python cloud_brain.py
```

首次运行会自动创建私有 Gist，控制台会打印 Gist ID。

### 4. 验证集成

```bash
python kylobrain_integration.py
```

---

## 与现有代码的接入点

### decision_pool_system.py（最重要）

在类的 `__init__` 加：
```python
from skills.kylobrain.kylobrain_integration import BrainHooks
self.brain = BrainHooks()
```

在决策执行前后加：
```python
# 执行前
hints = self.brain.on_task_start(decision_id, task_description)

# 执行后  
self.brain.on_task_complete(decision_id, outcome, success=True)
```

### skill_evolution/verifier.py

验证通过后加：
```python
from skills.kylobrain.kylobrain_integration import BrainHooks
hooks = BrainHooks()
hooks.on_skill_verified(skill_name, test_result)
```

### nanobot config.json（定时任务）

```json
{
  "tasks": [
    {
      "id": "brain_consolidation",
      "schedule": "0 3 * * *",
      "description": "每日凌晨记忆巩固",
      "action": "kylobrain",
      "params": {"action": "consolidate"}
    }
  ]
}
```

---

## 文件存储结构（运行后）

```
Kylopro-Nexus/
├── MEMORY.md              ← HOT记忆（已存在，现在自动管理大小）
└── brain/
    ├── warm/
    │   ├── episodes.jsonl   ← 任务历史
    │   ├── patterns.jsonl   ← 技能模式（直觉来源）
    │   ├── failures.jsonl   ← 失败记录（规避风险）
    │   └── consolidated.jsonl
    ├── cold_cache/
    │   ├── patterns.json    ← 云端数据本地缓存
    │   └── achievements.json
    └── cloud_config.json   ← 存着 Gist ID
```

---

## 不需要的东西（有意去掉）

- ❌ chromadb / 向量数据库：Jaccard相似度够用，省内存
- ❌ sentence-transformers：80MB模型，Windows上太重
- ❌ 自建服务器：GitHub Gist免费无限
- ❌ Redis / 数据库：纯文件，随时可读
- ❌ 实时同步：按需拉取，24h批量推送

---

## 扩展路线（之后做）

1. **图像理解接入**：截图 → 用LLM Vision分析 → 结果写入episodes
2. **ActionLoop闭环**：ide_bridge执行 → 捕获输出 → post_task_score
3. **antigravity上报**：平台操作结果 → 记录到云端world_model
4. **元认知仪表盘**：React页面展示大脑健康状态
