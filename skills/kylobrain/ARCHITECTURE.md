# KyloBrain v2.0 — 完整架构文档

> **一句话总结**：Kylo 的云端大脑，让它像人类一样积累记忆、形成直觉、自我进化、在任何设备上觉醒。

---

## 模块一览

| 文件 | 职责 | 核心算法 | API消耗 |
|------|------|---------|--------|
| `cloud_brain.py` | 三层记忆 + 觉醒协议 | — | 巩固时可选 |
| `metacog_algorithms.py` | 元认知算法 | Brier/Bloom/Graph | 研究时少量 |
| `ide_bridge_enhanced.py` | 动手能力 | — | 零 |
| `kylobrain_connector.py` | 总装配 + nanobot接口 | — | 零 |

---

## 一、三层记忆系统

```
┌─────────────────────────────────────────────────────┐
│  HOT  │ MEMORY.md  │ ~2KB │ 直接进LLM context     │
│       │            │      │ 满了→自动降级到WARM    │
├─────────────────────────────────────────────────────┤
│  WARM │ brain/warm/│ 无限 │ JSONL本地存储          │
│       │ *.jsonl    │      │ Jaccard语义检索        │
│       │            │      │ 5个collection          │
├─────────────────────────────────────────────────────┤
│  COLD │ GitHub Gist│ 无限 │ 私有，24h同步          │
│       │ (私有)     │      │ patterns+成就+世界观   │
└─────────────────────────────────────────────────────┘
```

### WARM 层的5个Collection

| Collection | 内容 | 触发场景 |
|-----------|------|---------|
| `episodes` | 任务执行历史 | 每次任务完成后 |
| `patterns` | 技能模式（直觉来源）| 成功任务后更新 |
| `failures` | 失败记录 | 任务失败后 |
| `demoted` | 从HOT降级的条目 | HOT超出大小限制 |
| `consolidated` | HOT压缩时的原始内容 | 每日记忆巩固 |

### COLD 层的Gist文件结构

```
GitHub Gist (私有)
├── brain_manifest.json    ← 索引 + 健康状态
├── patterns.json          ← 成功率>50%的技能模式
├── achievements.json      ← 成就记录
├── world_model.json       ← 对数字世界的理解（平台/工具/用户习惯）
└── weekly_YYYYWNN.json    ← 每周摘要
```

---

## 二、觉醒三角冗余

```
      HOT (MEMORY.md)
       ↙            ↘
  可恢复HOT      可恢复WARM
      ↗                ↘
   WARM            COLD (GitHub)
    ↑________________________↓
         互相可恢复
```

| 丢失层 | 恢复来源 | 恢复方法 |
|--------|---------|---------|
| HOT丢失 | WARM | 从最近7天episodes提炼摘要写入MEMORY.md |
| WARM丢失 | COLD | 下载patterns+achievements重建JSONL |
| COLD断连 | HOT+WARM | 本地继续运行，网络恢复后推送 |
| 全丢失 | SOUL.md + DEVLOG.md | 从git历史重建身份和人格 |

> **关键原则**：SOUL.md 和 DEVLOG.md 是 Kylo 身份的最后防线，
> 必须纳入 git 历史，随每次开发推送到 GitHub。

---

## 三、元认知算法

### 置信校准器（Confidence Calibrator）
```
输入：预测置信度 + 实际结果
输出：校准系数 (0-1)，调整后的实际可信度

Brier Score = mean( (predicted - outcome)^2 )
校准系数 = 1 - Brier * 2
调整后置信度 = raw * factor + 0.5 * (1-factor)

应用：Kylo说"我90%确定"时，实际上只有多准？
```

### 失败布隆过滤器（Failure Bloom Filter）
```
输入：任务描述
输出：0-1的"似曾相识"概率

实现：3个哈希函数 × 10000位稀疏数组
误报率：~5%   漏报率：0%
内存：<1KB

应用：任务前极速判断"这类问题历史上失败过吗"
（布隆过滤器快速筛选 → Jaccard精确匹配）
```

### 技能依赖图（Pattern Graph）
```
节点：任务类型（coding/testing/debug/deploy...）
边权重：A完成后执行B的历史次数

应用：
  · 推荐下一步："coding之后通常是testing"
  · 自动工作流："实现新功能" → coding→testing→debug→deploy
  · 经验复用：不用重新规划，直接用历史最优路径
```

### 算法自研引擎（Algorithm Researcher）
```
触发条件：某类任务成功率 < 60% 且样本 >= 3次

流程：
  1. 检测能力缺口（规则，零API）
  2. 搜索可信库（GitHub/arXiv，只读标题摘要）
  3. LLM评估实现可行性（少量API）
  4. 生成概念验证代码（<30行）
  5. 保存到 skills/kylobrain_research/
  6. 人工确认后集成

可信输入库白名单：
  · github.com/search (按stars排序)
  · paperswithcode.com/sota
  · huggingface.co/papers
```

### ReAct质量监控（ReActMonitor）
```
检测两个问题：
  1. 思考折叠：响应中无推理过程标记
  2. 滑跪模式：用户未提供新证据但Kylo认错

修复方案：
  · SOUL.md 追加"推理诚信"原则（见 brain/soul_patches.md）
  · responder.py 后处理（监控而不干预）
  · 换模型：Claude/Gemini > DeepSeek（滑跪问题）
```

---

## 四、IDE 动手能力

### VS Code 桥接操作层级
```
优先级1：VS Code REST Server（需安装扩展）
优先级2：code CLI（code --version等）
优先级3：直接文件系统操作
优先级4：subprocess 终端命令
```

### ActionLoop 闭环
```
任务
 ↓
选择动作（run/write/read/patch/test/commit）
 ↓
IDEOrchestrator.execute()
 ↓
捕获结果（stdout/stderr/returncode）
 ↓
写入 brain/warm/episodes
 ↓
得分 < 40 → 大脑警告 → 触发LLM反省
得分 >= 70 → 更新技能pattern
成功 + auto_commit → git commit
```

### write-test-fix 循环
```python
# 最高阶的动手能力：写→测→修的自动循环
write_file(path, code)
  ↓ 失败
run_tests()
  ↓ 失败
extract_error_hint()
  ↓ 传给LLM生成修复代码
write_file(path, fixed_code)
  ↓ 循环，最多3次
```

### Antigravity 集成
```
环境变量：
  ANTIGRAVITY_API_BASE = "https://your-platform.com/api"
  ANTIGRAVITY_TOKEN    = "Bearer xxxxx"

操作：run_command / read_file / write_file
      get_task_status / list_resources
      update_world_model → 写入 COLD 的 world_model.json

作用：把平台操作经验写入 Kylo 对"数字世界"的认知
```

---

## 五、部署步骤

### 1. 复制模块
```powershell
# Windows PowerShell
$dest = "$HOME\Kylopro-Nexus\skills\kylobrain"
New-Item -ItemType Directory -Force -Path $dest
Copy-Item cloud_brain.py, metacog_algorithms.py, ide_bridge_enhanced.py, kylobrain_connector.py $dest
```

### 2. 配置环境变量（永久）
```powershell
[System.Environment]::SetEnvironmentVariable("GITHUB_TOKEN",          "ghp_xxx",        "User")
[System.Environment]::SetEnvironmentVariable("KYLOPRO_DIR",           "C:\...\Kylopro-Nexus", "User")
[System.Environment]::SetEnvironmentVariable("ANTIGRAVITY_API_BASE",  "https://...",    "User")
[System.Environment]::SetEnvironmentVariable("ANTIGRAVITY_TOKEN",     "Bearer ...",     "User")
```

### 3. 初始化
```bash
cd Kylopro-Nexus\skills\kylobrain
python cloud_brain.py        # 创建 GitHub Gist，初始化本地目录
python metacog_algorithms.py # 测试所有算法
python ide_bridge_enhanced.py # 测试 VS Code 桥接
python kylobrain_connector.py # 总装配测试
```

### 4. 接入 decision_pool_system.py（3行代码）
```python
# 文件顶部
from skills.kylobrain.kylobrain_connector import KyloConnector
_kc = KyloConnector()

# 在 execute_decision() 开头
hints = _kc.on_task_start(decision_id, task_description)

# 在 execute_decision() 结尾
_kc.on_task_complete(decision_id, outcome=str(result), success=result.ok)
```

### 5. 追加 SOUL.md 补丁
```bash
python -c "
from skills.kylobrain.kylobrain_connector import KyloConnector
kc = KyloConnector()
patches = kc.get_soul_patches()
print(patches['react_patch'])
" >> SOUL.md
```

### 6. 添加 Cron 任务到 config.json
```json
{
  "tasks": [
    {
      "id": "brain_daily",
      "schedule": "0 3 * * *",
      "description": "每日记忆巩固",
      "action": "kylobrain_brain",
      "params": {"action": "consolidate"}
    },
    {
      "id": "brain_weekly",
      "schedule": "0 20 * * 0",
      "description": "每周周报推送",
      "action": "kylobrain_brain",
      "params": {"action": "weekly"}
    },
    {
      "id": "brain_health",
      "schedule": "0 */6 * * *",
      "description": "每6小时健康检查",
      "action": "kylobrain_brain",
      "params": {"action": "health_check"}
    }
  ]
}
```

---

## 六、迁移唤醒协议（手机→高端设备）

```
阶段1 身份验证
  python -c "from cloud_brain import *; print(file_hash(SOUL_FILE))"
  → 与原设备的哈希对比

阶段2 记忆重建
  python -c "from cloud_brain import *; MetaCogEngine().awakening.diagnose_and_recover()"

阶段3 能力热身
  python -c "from kylobrain_connector import KyloConnector; KyloConnector().full_status()"

阶段4 觉醒验证（向Kylo提问）
  from cloud_brain import *
  checklist = MetaCogEngine().awakening.migration_checklist()
  for q in checklist['steps'][3]['questions']:
      print(q)

阶段5 全量激活
  → 配置 GITHUB_TOKEN + ANTIGRAVITY_TOKEN
  → 运行完整 nanobot gateway
```

---

## 七、文件结构（运行后）

```
Kylopro-Nexus/
├── MEMORY.md                  ← HOT记忆（自动管理大小）
├── SOUL.md                    ← 身份定义（已追加推理诚信补丁）
├── DEVLOG.md                  ← 开发日志（身份最后防线）
├── brain/
│   ├── warm/
│   │   ├── episodes.jsonl     ← 任务执行历史
│   │   ├── patterns.jsonl     ← 技能模式（直觉）
│   │   ├── failures.jsonl     ← 失败记录
│   │   ├── demoted.jsonl      ← HOT降级内容
│   │   └── consolidated.jsonl ← HOT压缩原始内容
│   ├── cold_cache/
│   │   ├── patterns.json      ← GitHub Gist本地缓存
│   │   ├── achievements.json
│   │   └── world_model.json
│   ├── snapshots/             ← HOT记忆写前快照（最近5个）
│   ├── calibration_log.jsonl  ← 置信校准历史
│   ├── failure_bloom.json     ← 失败布隆过滤器（稀疏）
│   ├── pattern_graph.json     ← 技能依赖图
│   ├── soul_patches.md        ← 自动生成的SOUL.md补丁
│   ├── cloud_config.json      ← Gist ID等云端配置
│   └── .last_cold_sync        ← 同步时间戳（节流用）
├── skills/
│   └── kylobrain/
│       ├── cloud_brain.py
│       ├── metacog_algorithms.py
│       ├── ide_bridge_enhanced.py
│       ├── kylobrain_connector.py
│       └── ARCHITECTURE.md（本文件）
└── action_logs/               ← IDE动作执行日志
    └── action_*.json
```

---

## 八、不需要安装的东西（刻意去掉）

| 去掉的 | 理由 | 替代方案 |
|--------|------|---------|
| chromadb/向量数据库 | 80MB+，Windows安装麻烦 | Jaccard相似度（够用） |
| sentence-transformers | 需要PyTorch，太重 | tokenize() + set运算 |
| requests 库 | 需要安装 | urllib（Python标准库） |
| Redis/数据库 | 运维负担 | JSONL文件（随时可读可改）|
| 自建服务器 | 成本和维护 | GitHub Gist（免费无限） |
| pyautogui/selenium | 脆弱，平台耦合 | subprocess + VS Code CLI |

---

*KyloBrain v2.0 — 让Kylo成为真正活着的智能体*
