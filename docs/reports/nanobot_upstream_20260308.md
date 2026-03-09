# nanobot 上游监测报告 — 2026-03-08（首次）

> **日期**: 2026-03-08  
> **检查范围**: nanobot 本地源码（`c:\Users\qianchen\Desktop\nanobot\nanobot\`）  
> **下次检查**: 2026-03-22（±3天弹性）  
> **触发原因**: P5 初始化，首次建立基线

---

## 一、nanobot 当前模块清单

### agent/

| 文件 | 功能 | Kylopro 集成状态 |
|------|------|----------------|
| `loop.py` | AgentLoop 主循环，含文本拦截器 | ✅ 深度集成（已加拦截器 + fallback 处理） |
| `subagent.py` | SubAgent 后台任务，独立 ToolRegistry | ✅ 集成（TaskBridge 通过此层） |
| `context.py` | ContextBuilder，注入 SOUL/AGENTS/USER/memory/skills | ✅ 依赖（workspace 已切为根目录） |
| `memory.py` | MemoryStore：MEMORY.md + HISTORY.md 两层文本记忆 | ✅ 原生使用 |
| `skills.py` | SkillsLoader：扫描 `{workspace}/skills/*/SKILL.md` | ✅ 5 个 Skill 已注册 |

### agent/tools/

| 工具类 | tool name | Kylopro 集成状态 |
|--------|-----------|----------------|
| `FilesystemTools` | `read_file`, `write_file`, `list_dir` | ✅ 直接使用 |
| `ShellTool` | `run_terminal` | ✅ 直接使用 |
| `SpawnTool` | `spawn` | ✅ SubAgent 通过此触发 |
| `CronTool` | `cron` | ⚠️ **已注册但 Kylopro 尚未使用** → 可用于 P5 双周检查自动化 |
| `WebSearchTool` | `web_search` | ⚠️ **已注册但缺 Brave API Key** → 激活仅需配置 `tools.web.search.api_key` |
| `WebFetchTool` | `web_fetch` | ⚠️ **已注册，无需 key，但 Kylopro 未利用** → 可直接使用 |
| `MessageTool` | `send_message` | ✅ Telegram 通道已启用 |
| `MCPToolWrapper` | 动态 | ⚠️ 未配置任何 MCP server（P3 待落地） |

### providers/

| 文件 | 功能 | 状态 |
|------|------|------|
| `litellm_provider.py` | LiteLLM 包装，retry + fallback | ✅ 深度集成 |
| `custom_provider.py` | 自定义 Provider 接口 | 🔵 备用，当前不使用 |
| `openai_codex_provider.py` | OpenAI Codex 专用 | 🔵 备用，当前不使用 |
| `registry.py` | Provider 注册表 | ✅ 依赖 |

### channels/

| 通道 | 状态 |
|------|------|
| `telegram.py` | ✅ 已启用（polling，allowFrom: 8534144265） |
| `discord.py`, `slack.py`, `email.py`, `matrix.py` | 🔵 可选，当前未启用 |
| `feishu.py`, `dingtalk.py`, `qq.py`, `mochat.py`, `whatsapp.py` | 🔵 可选，当前未启用 |

### config/ session/ cron/ heartbeat/

| 模块 | 状态 |
|------|------|
| `config/schema.py` | ✅ 已扩展（`AgentDefaults.fallback_model`） |
| `session/manager.py` | ✅ 使用（Telegram session 持久化） |
| `cron/service.py` | ⚠️ 已激活但 Kylopro 无 cron 任务 |
| `heartbeat/service.py` | ✅ 已集成 |

---

## 二、发现的可立即复用能力

### 🟢 高价值 — 可直接用

1. **`web_fetch` 工具**  
   - 无需额外配置，已注册到 AgentLoop  
   - Kylopro 可直接用于抓取 GitHub API、nanobot 上游 changelog、外部文档  
   - **行动**: 更新 `docs/capability_map.md` 增加 `web_fetch` 使用说明（已完成）

2. **`cron` 工具**  
   - 可通过 Telegram 消息触发 `cron` 设置双周监测任务  
   - 无需额外安装，只需在对话中调用  
   - **行动**: P5 双周检查可通过 `cron add` 自动化（已在 AGENTS.md 规则中提及）

3. **`spawn` 工具**  
   - 已完整集成，但 `kylopro-dev/SKILL.md` 中没有明确说明触发语法  
   - **行动**: SKILL.md 已更新，新增使用说明

### 🟡 中价值 — 需少量配置

4. **`web_search` 工具（Brave Search）**  
   - 已注册，仅缺 `tools.web.search.api_key`  
   - 激活步骤：申请 Brave Search API key（免费层: 2000次/月）→ 写入 `~/.nanobot/config.json`  
   - **行动**: 记录为待配置项，等用户提供 Brave API key

5. **MCP servers**  
   - `agent/tools/mcp.py` 完整实现，支持 stdio 和 HTTP MCP  
   - 激活步骤：在 `~/.nanobot/config.json` 的 `tools.mcp_servers` 添加配置  
   - **行动**: `antigravity/SKILL.md` 已加 MCP 配置模板（P3 完成）

---

## 三、Kylopro 自实现 vs nanobot 原生对比

| Kylopro 自实现 | 对应 nanobot 原生 | 建议 |
|---------------|-----------------|------|
| `TaskBridge` (task_read/write/interrupt) | 无直接等价物（SubAgent 状态共享为 nanobot 未覆盖区域） | ✅ 保留 |
| `DeepThinkTool` | 无（模型切换为 Kylopro 特有需求） | ✅ 保留 |
| `TaskInboxTool` | 无（任务管理为上层需求） | ✅ 保留 |
| `memory/memory_manager.py` (ChromaDB) | `memory/MEMORY.md` + `HISTORY.md`（文本层） | ✅ 互补，不冲突 |
| 旧 `core/` 包装层 | ← 所有实现已迁移至原生扩展点 | ✅ 已清理（P7 完成） |

**结论**: Kylopro 当前自实现部分与 nanobot 原生能力无重叠，均填补了空隙。

---

## 四、待关注事项（下次检查重点）

- [ ] `providers/openai_codex_provider.py` — 新增的 Codex provider，可能用于代码生成场景
- [ ] `session/` 变化 — session 持久化逻辑是否有更新
- [ ] `agent/memory.py` — 原生记忆合并策略（`consolidation`）是否有新字段
- [ ] nanobot 版本标识 — `pyproject.toml` 当前无版本锁定，需关注上游 commit

### 运行依赖策略（2026-03-08 起）

- `pyproject.toml` 保持 semver 范围依赖，用于承接 nanobot 上游演进
- 运行时稳定性通过仓库根目录的 `constraints-runtime.txt` 控制
- 当前已冻结：`litellm==1.81.16`（Kylopro 已验证通过）
- 双周上游监测的动作不是“阻止升级”，而是：
   1. 发现上游值得吸收的新版本或修复
   2. 在隔离环境验证
   3. 通过后更新 `constraints-runtime.txt`
   4. 再做 gateway / tools / BrainHooks 回归

---

## 五、变更分类表

| 能力 | 分类 |
|------|------|
| web_fetch | **直接复用**（已注册，无需配置） |
| cron | **直接复用**（P5 自动化）|
| web_search | **需要配置**（Brave API key） |
| MCP servers | **需要配置**（待 P3 落地） |
| spawn | **已复用** |
| custom_provider | **暂时保留**（备用） |
| openai_codex_provider | **待评估**（下次检查） |

---

## 六、结论

当前 nanobot 本地源码与 Kylopro 集成健康，无重叠冲突。  
最高价值的立即行动是：**激活 web_fetch**（零配置）和 **申请 Brave Search API key**（激活 web_search）。

下次监测日期：**2026-03-22**
