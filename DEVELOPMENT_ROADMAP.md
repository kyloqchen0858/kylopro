# Kylopro × nanobot 开发路线图

> **最后更新**: 2026-03-08
> **核心原则**: 深入 nanobot 内部改造，而非在外面再包一层；默认中文优先；敏感信息只进专用保险柜，不进入普通记忆和对话输出

---

## 当前架构（已融合）

```
nanobot gateway（唯一生产入口）
  ├── AgentLoop + LiteLLMProvider
  │   ├── L1 主力: deepseek/deepseek-chat
  │   ├── L2 深度: deepseek/deepseek-reasoner (via deep_think)
  │   └── L3 fallback: minimax/abab6.5s-chat (auto on 429)
  ├── 文本工具调用拦截器 + retry/fallback
  ├── Kylopro 工具: task_inbox, deep_think, task_read/write/interrupt
  ├── TaskBridge: 主/子 Agent 状态共享
  ├── Skills: workspace/skills/*/SKILL.md
  ├── Context: SOUL.md + AGENTS.md + USER.md + MEMORY.md
  └── Channel: Telegram (polling)
```

配置单一来源: `~/.nanobot/config.json`
工作区: `Kylopro-Nexus/`（根目录，当前 `restrictToWorkspace=false`，以便读取用户桌面交付物；删除/修改工作区外文件仍需用户确认）
运行态: Windows 计划任务 `Kylopro-Nexus-Gateway` 会在登录后 15 秒自动执行 `start_gateway.bat`；无前台窗口不等于网关未运行，先查任务与进程，再判断是否掉线
开发入口: 后续统一先读 `docs/development/README.md`

---

## 已完成

| 编号 | 任务 | 完成日期 | 备注 |
|------|------|----------|------|
| P0 | 工具调用恢复 + 文本拦截器 | 2026-03-07 | loop.py + subagent.py 拦截器，AGENTS.md 去毒 |
| P0.5 | 模型稳定性 (retry + fallback) | 2026-03-07 | litellm_provider.py, schema.py, commands.py |
| P1 | TaskBridge 并发与中断 | 2026-03-07 | task_bridge.py + 3 个工具 + 2 条集成测试通过 |
| P7 | 架构收敛清理 | 2026-03-07 | 删 49 文件，core/ 精简为 3 文件 |
| — | 模型切换 + 阶梯调度 | 2026-03-08 | DeepSeek 主力，三层 L1/L2/L3 设计，README 重写 |
| P4 | 技能整合收尾 | 2026-03-08 | kylopro-dev/SKILL.md 重写，路径/优先级/工具表对齐 |
| P2 | 向量记忆实现 | 2026-03-08 | memory/memory_manager.py (ChromaDB CLI) + kylo-memory/SKILL.md |
| P6 | 自开发框架文档化 | 2026-03-08 | docs/capability_map.md 能力映射决策表 |
| P3 | Antigravity SKILL 重建 | 2026-03-08 | antigravity/SKILL.md 三级降级策略 + MCP 配置模板 |
| P5 | 上游监测首次报告 | 2026-03-08 | docs/reports/nanobot_upstream_20260308.md，下次: 2026-03-22 |
| — | 搜索+财务模块（Phase 7） | 2026-03-08 | Tavily+DDG+cost_tracker，4 个工具，¥50/周预算 |
| — | 技能进化路线图（Phase 7.5） | 2026-03-08 | docs/skills_evolution_roadmap.md，skill-evolution 技能 |
| — | 双脑架构 L0（Phase 8） | 2026-03-08 | LocalThinkTool，skills/local-brain，四层大脑 L0-L3，total 11 tools |
| — | L0 精细化 + HeartbeatService 本地集成（Phase 9） | 2026-03-08 | OllamaProvider，三模型路由（qwen2.5/coder/r1），心跳决策零成本 |

归档任务文件: `tasks/done/`

---

## 进行中

1. **P1 大脑与身体协同验证**
  - BrainHooks 已注入 HOT 记忆与 KyloBody 骨架
  - 已补充：运行态诊断原则写入自知层，避免把“无窗口”误判为“未运行”
  - 待做：真实 gateway 会话中的端到端验证

2. **通道收口**
  - Telegram 已验证
  - QQ 已验证
  - WhatsApp 当前因账号风控与重连问题降为待排查项，不作为稳定生产通道

2. **P2 向量记忆路线收敛**
  - `chromadb` 与 `sentence-transformers` 已安装到当前开发环境
  - 旧任务已整理进 `tasks/pending/20260308_p2_vector_memory_activation.md`
  - 下一步：把向量检索并入 KyloBrain WARM，而不是继续维护平行记忆体系

---

## 待开发（下一轮）

### ~~T0 — Ollama 本地脑部署~~（✅ 已完成）

Ollama 已安装，5 个模型已就绪。`OllamaProvider` 集成 nanobot `LLMProvider` 接口。
HeartbeatService `_decide` 阶段已改为 `qwen2.5:7b` 本地决策（零成本心跳）。

### T2 — 向量记忆并入 KyloBrain

依赖已安装，向量记忆仍未进入生产链路，现已整理为独立待办：
`tasks/pending/20260308_p2_vector_memory_activation.md`

当前开发环境已完成：
```
.venv\Scripts\python.exe -m pip install chromadb sentence-transformers
```
下一步不再是“装依赖”，而是“接入 WarmMemory 搜索链路”。

### T1 — SearXNG 自托管搜索（需 Docker）

完整部署方案见 `docs/skills_evolution_roadmap.md` T1 节。
Docker 可用时，一行命令部署：`docker run -d -p 8888:8080 searxng/searxng`

### 双周上游监测（持续）

下次检查：2026-03-22 → 输出 `docs/reports/nanobot_upstream_20260322.md`

依赖策略：
当前采用“上游范围依赖 + 运行时约束文件”双层方案。
`pyproject.toml` 保持兼容范围，`constraints-runtime.txt` 只冻结已验证的运行版本；双周监测若发现值得吸收的更新，先验证，再提升约束版本。

---

## 建议执行顺序（下一轮）

1. **P1 大脑与身体协同验证**
2. **T2 向量记忆路线收敛**
3. **T1 SearXNG**（Docker 可用时，一行启动）
4. **P5 双周监测**（2026-03-22）

> 注：旧的 Python 丢失告警已不再作为当前主阻塞项，当前优先级回到能力协同与任务收敛。

---

## 长期原则

- 新功能优先落在 nanobot 原生扩展点：`SKILL.md`、`Tool`、`config.json`、`CronTool`、`SpawnTool`
- 不在已废弃的 `core/` 旧包装层堆新功能
- 缺资源（token/账号/程序/权限）时先向用户索要
- 开发新功能前先查 `docs/capability_map.md` 和最近一次上游监测报告
