# Kylopro-Nexus

Kylopro-Nexus 是运行在 nanobot 原生链路上的自治开发工作区。当前重点不是在外层再包一套平行框架，而是让 Kylo 的大脑、身体、任务状态和记忆系统在同一个根工作区里形成闭环。

---

## 当前状态

- 运行入口：`nanobot gateway`
- 启动脚本：`start_gateway.bat`（唯一生产脚本）
- 工作区：`Kylopro-Nexus/` 根目录
- 大脑：KyloBrain（HOT/WARM/COLD + 元认知 + BrainHooks）
- 身体：文件工具、终端、TaskBridge、screen、local_think、deep_think
- 定时任务：每日巩固、每周周报、每 6 小时健康检查
- 当前未完成方向：见 `tasks/pending/`

---

## Kylo 的骨架与四肢

### 骨架

| 目录 | 作用 |
|------|------|
| `core/` | 运行时接线层：工具注册、BrainHooks、本地 provider |
| `kylo_tools/` | TaskBridge 共享状态桥 |
| `skills/` | 给模型看的技能手册与 always-on 规则 |
| `brain/` | KyloBrain 记忆、快照、动作日志 |
| `tasks/` | 收件箱、待办、完成归档、活动任务状态 |
| `docs/` | 架构文档、路线图、报告 |
| `data/` | 本地配置、财务状态、运行数据 |

### 四肢

| 能力 | 入口 | 说明 |
|------|------|------|
| 文件读写 | nanobot 原生文件工具 | 读、改、列目录 |
| 命令执行 | `exec` / 终端 | 运行测试、脚本、构建命令 |
| 长任务状态 | `task_read` / `task_write` / `task_interrupt` | 通过 TaskBridge 共享主子任务状态 |
| 深度推理 | `deep_think` | 切换到深度模型做复杂分析 |
| 本地脑 | `local_think` | 零成本本地模型，用于计算/摘要/脚本 |
| 屏幕操作 | `screen` | 截图、窗口、输入、点击 |
| 大脑记忆 | `kylobrain` | 任务前直觉、任务后评分、记忆写入与回忆 |

### 协同闭环

```text
用户请求
  → BrainHooks 注入 HOT 记忆 + KyloBody 骨架
  → AgentLoop 判断并选择工具
  → TaskBridge / screen / 文件工具 / 本地脑 执行
  → KyloBrain 记录到 WARM episodes
  → Cron 做每日巩固与周报
```

---

## 关键模块

| 文件 | 作用 |
|------|------|
| `tools_init.py` | 工作区工具注册入口，安装 BrainHooks |
| `core/kylopro_tools.py` | 自定义工具注册：TaskBridge、deep_think、local_think、screen、kylobrain |
| `core/brain_hooks.py` | 把大脑上下文和身体地图注入 prompt，并自动记录 episodes |
| `kylo_tools/task_bridge.py` | 主/子任务共享状态，已支持原子写入与重试 |
| `skills/kylobrain/` | 三层记忆、元认知、IDE 编排、大脑总装配 |
| `DEVLOG.md` | 跨对话恢复用的开发日志 |
| `DEVELOPMENT_ROADMAP.md` | 当前方向与长期路线 |

---

## 目录约定

```text
Kylopro-Nexus/
├── core/                  # 生产级接线层与工具
├── kylo_tools/            # TaskBridge 等共享执行组件
├── skills/                # nanobot 技能手册
├── brain/                 # KyloBrain 数据目录
├── tasks/
│   ├── pending/           # 当前未完成任务
│   ├── done/              # 已归档完成任务
│   └── active_task.json   # 主/子任务共享状态
├── docs/                  # 文档与报告
├── data/                  # 本地配置与状态数据
├── tests/                 # 集成与回归测试
└── README.md
```

---

## 当前待办

当前未完成工作已经整理到：

- `tasks/pending/20260308_p1_brain_body_sync.md`
- `tasks/pending/20260308_p2_vector_memory_activation.md`

---

## 启动脚本约定

- `start_gateway.bat`：唯一生产启动脚本，支持 `/NODELAY` 与 `/ONESHOT`
- `clean_restart_gateway.bat`：清理残留进程后委托 `start_gateway.bat` 启动，避免维护第二套启动逻辑
- `register_gateway_service.bat`：把 `start_gateway.bat` 注册为登录自启任务
- `start_production.bat`：仅保留为历史兼容包装，不再承载独立逻辑

多通道配置与网关操作手册见：`docs/gateway_channels_playbook.md`
开发入口文件夹见：`docs/development/`

---

## 新对话恢复顺序

1. 先读 `docs/development/README.md`
2. 再读 `docs/development/CURRENT_STATUS.md`
3. 再读 `docs/development/ROADMAP.md`
4. 然后读 `tasks/pending/`
5. 需要运行细节时再读 `AGENTS.md` 与 `docs/gateway_channels_playbook.md`

---

## 备注

- 不再使用旧的 `workspace/` 子目录语义，当前工作区就是仓库根目录。
- `skills_old/` 是历史归档，不是当前生产能力来源。
- GitHub 云端冷记忆已可用，前提是 `.env` 中已配置 `GITHUB_TOKEN`。