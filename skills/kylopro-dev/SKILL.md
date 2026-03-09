---
name: kylopro-dev
description: "Kylopro 自主开发技能 — 在 Kylopro-Nexus 项目上进行代码开发和自我进化"
metadata: {"nanobot":{"always":true}}
---

# Kylopro 开发指南

## 项目结构（workspace = Kylopro-Nexus 根目录）

工作区直接是 `Kylopro-Nexus/` 根目录，所有路径相对于此：

| 目录 | 用途 |
|------|------|
| `core/` | 生产 Python 扩展：`kylopro_tools.py`（工具注册）、`config.py` |
| `kylo_tools/` | TaskBridge 共享状态桥（`task_bridge.py`） |
| `skills/` | nanobot 技能目录（`*/SKILL.md`，由 SkillsLoader 扫描） |
| `memory/` | 持久记忆：`MEMORY.md`（长期事实）、`HISTORY.md`（事件日志）、`vector_store/`（向量记忆） |
| `tasks/` | 任务文件：`pending/`、`done/`、`active_task.json` |
| `docs/` | 文档、报告、规范（`docs/reports/` for 双周报告，`docs/capability_map.md`） |
| `tests/` | 测试文件 |
| `data/` | 数据与配置 |

nanobot 框架代码在 `../nanobot/`（工作区上一级）。

## 需求归属判断（先判断再动手）

收到任何开发需求，先按此顺序判断落到哪一层：

1. **nanobot 原生** — `AgentLoop`、`ToolRegistry`、`SkillsLoader`、`MemoryStore`、`CronTool`、`SpawnTool`、`WebSearchTool`、`WebFetchTool`、MCP tools
2. **规则层** — `SOUL.md`、`AGENTS.md`、`USER.md`、`SKILL.md`
3. **自定义 Tool** — `core/kylopro_tools.py` 新增 Tool 类
4. **MCP / 外部程序** — 需要 MCP server 或外部 binary
5. **用户资源** — 需要 token、账号、程序、权限（先索取，不假设）

参考 `docs/capability_map.md` — 完整能力映射表。

## 开发工作流

1. **查能力映射**: 先看 `docs/capability_map.md`，确认 nanobot 是否已有原生能力
2. **查上游报告**: 看 `docs/reports/` 最新一份监测报告，避免重复造轮子
3. **小步验证**: 新代码先在 `sandbox/` 或直接在目标文件小步测试
4. **职责分离**: `SKILL.md` 负责规则，`Tool` 类负责 Python 执行，两者不混用
5. **缺资源先索取**: 缺 token/账号/程序时先向用户要，不假装已具备
6. **记录完成**: 完成后更新 DEVLOG.md + DEVELOPMENT_ROADMAP.md + tasks 状态

## nanobot 当前已知原生工具

| 工具 | 类 | 文件 |
|------|----|------|
| `read_file` / `write_file` / `list_dir` | FilesystemTools | `agent/tools/filesystem.py` |
| `run_terminal` | ShellTool | `agent/tools/shell.py` |
| `spawn` | SpawnTool | `agent/tools/spawn.py` |
| `cron` | CronTool | `agent/tools/cron.py` |
| `web_search` | WebSearchTool | `agent/tools/web.py` |
| `web_fetch` | WebFetchTool | `agent/tools/web.py` |
| `send_message` | MessageTool | `agent/tools/message.py` |
| MCP tools | MCPToolWrapper | `agent/tools/mcp.py` |

## 当前开发优先级（2026-03-08）

已完成：P0、P0.5、P1、P7、P4（部分）、模型切换+阶梯调度

待开发（按建议顺序）：
1. P2: 向量记忆 — `memory/memory_manager.py` + `skills/kylo-memory/SKILL.md` 完善
2. P6: 自开发框架文档 — `docs/capability_map.md`
3. P3: Antigravity MCP-first 重建 — `skills/antigravity/SKILL.md`
4. P5: nanobot 上游双周监测 — `docs/reports/nanobot_upstream_YYYYMMDD.md`

## 重要提醒

- 生产 Python: `c:\Users\qianchen\Desktop\nanobot\venv\Scripts\python.exe`
- 生产入口: `nanobot gateway`（不使用 `.venv`）
- 主力模型: `deepseek/deepseek-chat`，深度: `deepseek-reasoner`，fallback: `minimax/abab6.5s-chat`
- workspace 已改为 Kylopro-Nexus 根目录（`restrictToWorkspace=true`）
- AppData\Python312 可能自动拉起旧进程，启动前先杀所有 python 进程
