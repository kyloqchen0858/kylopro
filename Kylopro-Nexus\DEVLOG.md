# Kylopro-Nexus 开发日志

> **用途**：跨对话上下文记忆。新对话开始时，将此文件 + task.md 发给 AI 即可恢复所有进度。
> **项目位置**：`c:\Users\qianchen\Desktop\Kylopro-Nexus\`

---

## Phase 1 — 2026-03-06

### 完成内容

**环境决策**：Windows Python venv（现有 nanobot venv 基础上扩展，暂不 Docker）

**已创建文件**：
| 文件 | 说明 |
|------|------|
| `core/provider.py` | 双核路由大脑（DeepSeek + Ollama 自动切换） |
| `core/engine.py` | 主控循环（封装 nanobot AgentLoop，CLI 交互） |
| `skills/telegram_notify/notify.py` | Telegram 主动推送技能 |
| `skills/telegram_notify/SKILL.md` | 技能定义文件（nanobot 格式） |
| `requirements.txt` | 依赖清单 |
| `setup.bat` | Windows 一键初始化 |
| `.env.example` | 密钥模板 |

**关键设计决策**：
- `core/provider.py` 中 `_load_nanobot_config()` 自动读取 `~/.nanobot/config.json`
  → Telegram token/chat_id 和 DeepSeek API key 无需重复配置
- Gemini-CLI 协作接口预留为 `spawn_gemini_cli()` 占位方法（Phase 3 激活）
- 多厂商扩展槽 `PROVIDER_SLOTS` 字典在 `provider.py` 中，填入 `.env` 对应 key 即激活
- 安全拦截 `_safety_check()` 硬编码在 provider 层，不可被 Kylopro 绕过

**已知配置**（读取自 `~/.nanobot/config.json`）：
- DeepSeek API Key: `sk-8df1...ac4e`（测试用，10元额度）
- 默认模型: `deepseek/deepseek-reasoner`
- Telegram: enabled, bot token + allowFrom user ID 已配置

### 待验证（Phase 1 结束前）
- [ ] `pip install -r requirements.txt` 成功
- [ ] `python -m core.engine` 启动，双核连通性测试通过
- [ ] Telegram 推送测试成功（`python skills/telegram_notify/notify.py`）

### ❌ 失败复盘 (2026-03-07 00:20)

**现象**：Kylopro 在改动后陷入“复读机”状态，回复“我是 AI 助手，无法主动采取行动”，即便环境已配置 RPA。

**根本原因**：
1. **灵魂缺失**：`nanobot` 框架因缺少 `SOUL.md`，导致 Agent 在执行任务时退化为默认受限人格。
2. **能力断层**：`TaskDispatcher` 原有的子任务执行仅调用了 LLM 聊天接口，未传递任何 Tools 定义，导致后台执行时“没手没脚”。
3. **状态隔离**：前台 CLI 与后台 Inbox 监控未共享 Engine 单例，导致工具状态不一致。

**修复方案**：
- 创建 `SOUL.md` 强制注入高权限人格。
- 将 `TaskDispatcher` 的 `analyze` 和 `modify` 逻辑重构为调用完整的 `AgentLoop`。
- 实现 `get_engine()` 单例模式统一全局大脑。

---

## Phase 2 — 2026-03-07 (自主进化增强)

**核心架构修复：脑肢协同 (Brain-Limb Integration)**：
- **物理接线 (`core/tools.py`)**: 将 `IDEBridge`, `VisionRPA`, `TaskInbox` 封装为 `nanobot` 标准 Tool，并注册到 `AgentLoop`。
- **灵魂注入 (`core/engine.py`)**: 为 `AgentLoop` 注入 Kylopro 专用系统指令，强化“高度自治、优先动手动脚”的身份认同。
- **路由优化**: 扩展了 `needs_tools` 关键词过滤，包含“开发”、“操作”、“自己”等意图，确保复杂请求能进入工具执行环境。
- **自主循环**: 实现了 `TaskInbox` 启动时自动运行，打通了“大模型生成需求 -> 写入 Inbox -> 调度器执行 -> 完成”的递归进化闭环。

**已创建文件**：
| 文件 | 说明 |
|------|------|
| `core/tools.py` | 技能与框架的适配层 (Tool Wrapper) |

**关键决策**：
- 默认将 `AgentLoop` 的 `workspace` 设为项目根目录，赋予 Kylopro 修改自身代码的最高权限。
- 强制路由：任何包含“自己”、“实验”或显式 `[complex]` 前缀的请求，必须开启工具调用。

### 待验证
- [x] `python -m core.engine` 启动后 `TaskInbox` 是否自动运行
- [ ] 测试指令：“帮我写个 markdown 存入 inbox，内容是优化 provider.py 的日志输出”
- [ ] 验证 Vision RPA 在 Windows 下的截图权限问题

---

## Phase 3 — 未来

- Gemini-CLI 协作激活
- Docker 容器化部署
- 财务/额度监控模块
