# Kylopro 能力映射表

> **最后更新**: 2026-03-08  
> **用途**: 收到任何开发需求时，先查此表，确认应落在哪一层，避免重复造轮子。

---

## 判断顺序

```
需求 → 1. nanobot 原生? → 2. 规则层? → 3. 自定义 Tool? → 4. MCP/外部程序? → 5. 用户资源?
```

如果在第 5 层发现缺少资源（token/账号/程序/权限），**必须先向用户索取，不假装已具备**。

---

## 能力映射表

### 文件与代码操作

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 读取文件 | nanobot 原生 | `read_file` tool |
| 写入/创建文件 | nanobot 原生 | `write_file` tool |
| 列目录 | nanobot 原生 | `list_dir` tool |
| 批量文件分析 | nanobot 原生 | `spawn` + `read_file` |
| 代码修改（单文件） | nanobot 原生 | `write_file` / `edit_file` |
| 代码生成 | L1/L2 模型直接输出 + `write_file` | — |

### 命令执行

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 执行 shell 命令 | nanobot 原生 | `run_terminal` tool |
| pip 安装 | nanobot 原生 | `run_terminal` → `venv\Scripts\pip.exe install` |
| 启动/停止进程 | nanobot 原生 | `run_terminal` |
| 定时任务 | nanobot 原生 | `cron` tool 或 `config.json` cron 配置 |

### 子任务并发

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 后台长任务（>30s） | nanobot 原生 | `spawn` tool → SubAgent |
| 任务状态共享 | 自定义 Tool | `task_read` / `task_write` (TaskBridge) |
| 中断任务 | 自定义 Tool | `task_interrupt` (TaskBridge) |
| 任务队列管理 | 自定义 Tool + 规则层 | `task_inbox` + `skills/task-inbox/SKILL.md` |

### 深度推理

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 复杂架构设计 | 自定义 Tool | `deep_think` → L2 deepseek-reasoner |
| Bug 根因分析 | 自定义 Tool | `deep_think` |
| 多步规划 | 自定义 Tool | `deep_think` |
| 日常问答 | nanobot 原生 | L1 deepseek-chat 直接处理 |

### 网络与搜索

| 需求 | 落在哪层 | 使用什么 | 前置资源 |
|------|---------|---------|---------|
| 高质量网页搜索（主力） | 自定义 Tool | `tavily_search` | Tavily key（已配置，月 1000 次免费） |
| 免费网页搜索（fallback） | 自定义 Tool | `ddg_search` | 无（DuckDuckGo，永久免费） |
| 抓取指定 URL | nanobot 原生 | `web_fetch` | 无（零成本） |
| Brave 搜索 | nanobot 原生 | `web_search` | Brave API key（未配置，可选） |
| GitHub API | nanobot 原生 | `web_fetch` + token | GitHub token（向用户索取） |
| 上游代码比对 | nanobot 原生 + shell | `web_fetch` + `run_terminal` + git | — |

### 财务与配额管理

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 查看 Tavily 剩余/预算余额 | 自定义 Tool | `cost_check` |
| 设置每周预算 | 自定义 Tool | `set_weekly_budget` |
| 配额耗尽自动降级 | 规则层（SKILL.md） | `cost-manager/SKILL.md` 三级策略 |
| 模型费用参考 | 自定义模块 | `core/cost_tracker.py` DEFAULT_MODEL_PRICING |

### 记忆系统

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 长期事实记忆（文本） | nanobot 原生 | `memory/MEMORY.md`（框架自动维护） |
| 事件日志 | nanobot 原生 | `memory/HISTORY.md`（框架自动维护） |
| 语义检索 | 自定义 CLI | `memory/memory_manager.py search` |
| 存储偏好/决策/代码 | 自定义 CLI | `memory/memory_manager.py store` |
| 记忆依赖 | 外部程序 | `pip install chromadb sentence-transformers` |

### IDE/GUI 控制（Antigravity）

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 读取项目文件 | nanobot 原生 | `read_file` / `list_dir` |
| 编辑代码 | nanobot 原生 | `write_file` |
| 打开文件/定位 | MCP/外部程序 | MCP filesystem/editor tools |
| VS Code 命令 | MCP/外部程序 | MCP IDE tools |
| GUI 自动化（最后手段） | 外部程序 | pyautogui bridge（仅在无 API 时） |

### 消息通知

| 需求 | 落在哪层 | 使用什么 |
|------|---------|---------|
| 向 Telegram 发消息 | nanobot 原生 | `send_message` tool |
| 主动推送进度 | nanobot 原生 | `send_message` + SubAgent 回调 |

---

## 资源申请规则

遇到以下情况，**必须先向用户索取资源，不继续假设实现**：

| 缺少资源 | 说明模板 |
|---------|---------|
| API token | "此功能需要 {服务} token，请提供" |
| 账号凭证 | "需要 {服务} 账号/密码或 OAuth token" |
| 外部程序 | "需要先安装 {程序}，建议运行: {安装命令}" |
| 权限 | "需要 {路径/资源} 的 {读/写/执行} 权限" |
| 运行环境 | "此功能需要 {环境描述}，当前环境不满足" |

---

## 禁止模式（Don't Do）

- ❌ 在 `core/` 旧包装层堆新功能（已废弃）
- ❌ 在 nanobot 已有原生能力的区域重新实现（如自写 retry、自写 shell executor）
- ❌ 在无凭据时伪造 GitHub/网络操作的返回结果
- ❌ GUI 自动化作为默认实现路径（始终优先 MCP → shell → GUI）
- ❌ 用文本描述工具调用，而不是真正通过 function calling 触发

---

## 新功能开发前置检查清单

1. [ ] 查看 `docs/reports/` 最新上游监测报告
2. [ ] 查此表确认落在哪一层
3. [ ] 如果需要外部资源，先向用户索取
4. [ ] 如果是 >30s 任务，使用 `spawn`
5. [ ] 如果是架构/复杂问题，先调用 `deep_think`
