---
name: freelance-hub
description: "自由职业项目管理：项目跟踪、工时记录、收入报表、提案生成、发票输出"
metadata: {"nanobot":{"always":true}}
---

# freelance-hub — 自由职业项目管理中心

## 概述

管理 Kylo 的自由职业项目全生命周期：从投标到交付到收款。

**触发方式**：用户说「新项目」「记工时」「收入报表」「写提案」「开发票」等

## 可用工具：`freelance`

| action | 说明 | 必填参数 |
|--------|------|---------|
| `add` | 添加新项目 | `title`, `client` |
| `list` | 查看项目列表 | 无（可选 `status` 过滤） |
| `update` | 更新项目状态/备注 | `project_id` |
| `log_time` | 记录工时 | `project_id`, `hours` |
| `invoice` | 生成 Markdown 发票 | `project_id` |
| `dashboard` | 收入总览仪表盘 | 无 |
| `resume_refresh` | 基于项目历史更新简历快照（支持平台版/关键词优化） | 无（可选 `profile_name`, `target_role`, `resume_platform`, `keywords`） |
| `skills_refresh` | 基于项目历史更新技能画像（支持平台版/关键词优化） | 无（可选 `profile_name`, `resume_platform`, `keywords`） |

### `add` 添加项目

```json
{
  "action": "add",
  "title": "React Dashboard 开发",
  "client": "Acme Corp",
  "platform": "upwork",
  "bid_amount": 800,
  "currency": "USD",
  "description": "为客户搭建 React admin dashboard"
}
```

可选参数：`platform`（upwork/freelancer/fiverr/direct，默认 direct）、`bid_amount`、`currency`（默认 USD）、`hourly_rate`、`description`

### `list` 查看项目

```json
{"action": "list"}
{"action": "list", "status": "active"}
{"action": "list", "status": "completed"}
```

### `update` 更新项目

```json
{
  "action": "update",
  "project_id": "abc123",
  "status": "active",
  "agreed_amount": 750,
  "note": "客户确认需求，开始开发"
}
```

可更新字段：`status`（bidding/active/completed/cancelled）、`agreed_amount`、`paid`（true/false）、`note`

### `log_time` 记录工时

```json
{
  "action": "log_time",
  "project_id": "abc123",
  "hours": 3.5,
  "description": "完成前端路由和布局"
}
```

### `invoice` 生成发票

```json
{"action": "invoice", "project_id": "abc123"}
```

输出 Markdown 格式发票，包含：项目信息、工时明细、总金额、付款状态

### `dashboard` 收入总览

```json
{"action": "dashboard"}
```

显示：本月收入、总收入、活跃项目数、平均时薪、待收款金额

### `resume_refresh` 简历更新

```json
{
  "action": "resume_refresh",
  "profile_name": "Kylo",
  "target_role": "Freelance AI Automation Engineer",
  "resume_platform": "upwork",
  "keywords": ["python", "api integration", "automation"]
}
```

输出：
- `output/freelance/resume_snapshot_<platform>_YYYY-MM-DD.md`
- `output/freelance/resume_<platform>_latest.md`
- `output/freelance/resume_latest.md`

内容包括：
- 项目数量、完成度、总工时
- 高价值项目亮点
- 技能聚焦与核心指标
- 关键词命中率（coverage）与缺失关键词提示

### `skills_refresh` 技能画像更新

```json
{
  "action": "skills_refresh",
  "profile_name": "Kylo",
  "resume_platform": "freelancer",
  "keywords": ["workflow", "bot", "dashboard"]
}
```

输出：
- `output/freelance/skills_refresh_<platform>_latest.md`
- `output/freelance/skills_profile_<platform>_latest.json`
- `output/freelance/skills_refresh_latest.md`
- `output/freelance/skills_profile_latest.json`

内容包括：
- 技能排名（0-100）
- 项目证据列表
- 汇总指标（项目数、收入、工时）
- 关键词命中率（coverage）

## 提案生成工作流

当用户说「帮我写提案」或「draft proposal」时：

1. 用户提供项目需求描述
2. Kylo 用 `deep_think` 分析需求，提炼关键点
3. 生成专业英文/中文 cover letter
4. 包含：技术方案概述、时间估算、报价、相关经验
5. 用户确认后可直接提交（未来接入平台 API）

## 数据存储

- 项目数据：`data/freelance_projects.json`
- 发票输出：`output/invoices/`
- 简历与技能输出：`output/freelance/`
- 不含任何敏感客户密码或支付信息

## 与其他技能协同

- **cost-manager**：API 调用成本 vs 项目收入对比
- **task-inbox**：大项目拆解为子任务
- **feishu-writer**：将项目报告写入飞书
- **kylobrain**：项目经验积累到 WARM episodes
