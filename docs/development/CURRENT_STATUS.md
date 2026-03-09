# 当前状态

> 更新：2026-03-10 Phase 11.6b

## 已验证能力

- `nanobot gateway` 仍是唯一生产入口，`start_gateway.bat` 是唯一生产启动脚本
- Telegram 通道已验证，QQ 通道已验证
- BrainHooks 已接入运行时，WARM 读取端与 episode 写入端都已打通
- OAuth2VaultDB 已完成 Windows 保护、WAL 模式和 stdlib fallback 修补
- 飞书 OAuth2 链路代码已跑通：凭证保险箱、AuthMiddleware、文档创建、消息发送
- Freelance 工作流已支持项目跟踪、工时、发票、简历快照、技能画像
- 自知层已补充能力域、工具降级路径、失败经验沉淀

## 本轮阶段结论

- **Phase 11.4**：工具降级体系、自知层增强、技能整合完成
- **Phase 11.5**：L0/L1/L2 记忆认同系统与桌面操作能力已落地
- **Phase 11.6**：搜索入口合并、L0 路径修复、SOUL 风格自然化完成
- **Phase 11.6b**：追问模板误判修复、MCP 安全经验写入脑循环、操作文档补齐

## 核心诊断

| 维度 | 状态 | 当前瓶颈 |
|------|------|---------|
| 骨架 | 90% | 需要继续压缩重复入口与历史副本 |
| 大脑 | 95% | 还缺 L1/L2 定时提炼的正式生产调度 |
| 灵魂 | ✅ v5.1 | 需要继续验证真实对话自然度 |
| 交互 | 55% | 消息合并、打断、silent progress 仍未代码化 |
| 安全 | 65% | 规则层完整，代码级 `policy_check()` 仍缺 |
| 外部能力 | 60% | 飞书链路完成，Notion/GitHub 外部动作还未接通 |

## 当前阻塞

1. 飞书真实新凭证仍待用户提供 `app_id/app_secret` 做新一轮端到端验证
2. MessageCoalescer、Preemption、silent tool progress 仍在设计稿阶段
3. L1/L2 记忆提炼已有代码，但尚未配置 cron 进入稳定生产循环

## Git 与文件整理状态

- 当前工作区分为两个 Git 边界：顶层 `nanobot/` 与嵌套仓库 `Kylopro-Nexus/`
- `Kylopro-Nexus/.env`、`brain/`、`data/`、`logs/`、`tasks/`、`output/` 继续留在本地，不进 Git
- `core/`、`kylo_tools/`、`skills/`、`docs/`、`tests/`、`SOUL.md`、`AGENTS.md` 是本轮应同步到 GitHub 的主要资产

## 下一步

1. 配置并验证飞书新凭证，确认外部平台真实动作闭环
2. 把 MessageCoalescer、Preemption、ToolResult silent 落到代码
3. 为 L1/L2 记忆提炼补上 cron 调度并验证首次产出
4. 继续推进 Tool Policy、输入净化、Notion OAuth2、Session 压缩

## 通道状态

| 通道 | 状态 | 风险 |
|------|------|------|
| Telegram | ✅ 主通道 | polling 单实例冲突，需先释放旧会话 |
| QQ | ✅ 辅通道 | 仍依赖外部平台配置正确性 |
| WhatsApp | ⚠️ 降级待排查 | bridge 不稳定，暂不作为稳定生产通道 |

## 敏感信息策略

- `~/.nanobot/config.json` 是真实运行配置源，不进入仓库
- `Kylopro-Nexus/.env`、`brain/vault/`、`data/` 仅本地保存
- token、secret、API key 只能进入保险箱或本地环境变量，不进入普通文档、日志和 episode 正文