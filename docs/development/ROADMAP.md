# 当前路线图

> 更新：2026-03-10 Phase 11.6b

## 当前阶段

### Phase 11.4 — 工具降级体系 + 自知层增强 ✅
- 飞书文档 URL 修复
- 能力域 + 降级路径注入 prompt
- kylo-memory / cost-manager 完成整合收口

### Phase 11.5 — 记忆认同系统 + 桌面操作 ✅
- L0/L1/L2 记忆认同系统完成
- DesktopTool 与外部求援能力已接入
- 设计文档与操作文档已补齐

### Phase 11.6 — 搜索合并 + 风格修复 + L0 路径修复 ✅
- `web_search` 统一入口替代 Tavily/DDG 手工选择
- SOUL 风格自然化
- L0 路径修复为仓库相对路径

### Phase 11.6b — 追问修复 + MCP 安全 + 脑循环经验录入 ✅
- `_is_ambiguous_instruction()` 不再用模板绕过 LLM
- MCP 配置错误经验与搜索引擎误用经验已写入 WARM
- 记忆系统操作文档补全

### Phase 11.7 — 交互层代码化（当前主线）
- MessageCoalescer 消息合并（3 秒窗口）
- Preemption 检查点（执行中打断）
- ToolResult silent / progress 过滤
- 行为评分器（追问、打断、成功率）

### Phase 12 — 安全加固 + 多平台
- Tool Policy 代码约束（`policy_check()` 实际拒绝未授权操作）
- 外部内容 `[EXTERNAL_CONTENT]` 标记
- 审计日志 `data/action_log.jsonl`
- Notion OAuth2 适配器
- Session 压缩（L0 本地跑）

## 当前优先级

1. **飞书新凭证验证**：完成新的 `app_id/app_secret` 实测，重新验证外部动作闭环
2. **交互层代码化**：把 MessageCoalescer、Preemption、silent progress 从设计稿落地
3. **记忆调度生产化**：补齐 L1/L2 cron，验证 identity synthesis 首次产出
4. **安全硬边界**：实现 Tool Policy、输入净化、审计日志

## GitHub 同步原则

1. 只同步源码、技能手册、测试、架构文档
2. 不同步 `.env`、`brain/`、`data/`、`logs/`、`tasks/`、`output/`
3. 顶层 `nanobot` 与嵌套 `Kylopro-Nexus` 分别提交，避免混淆仓库边界
4. 推送前必须做一次密钥扫描与忽略规则检查

## 当前最大瓶颈

1. **交互品质仍未真正代码化**：消息合并和中断能力还在设计稿阶段
2. **生产验证仍依赖真实凭证**：飞书链路代码完整，但新凭证尚未完成实测
3. **安全层还缺代码硬阻断**：文档规则完整，执行时的 policy gate 仍未落地