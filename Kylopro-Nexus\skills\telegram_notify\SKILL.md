---
name: telegram_notify
description: 让 Kylopro 主动向你的 Telegram 推送消息（任务完成、告警、日报汇报）
always: false
metadata: |
  {"nanobot": {"requires": {"env": ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]}}}
---

# Skill: telegram_notify — Kylopro 主动推送

## 功能说明

当你完成任务、遇到异常或需要汇报时，Kylopro 可以主动向你的 Telegram 发送消息。

**注意**：Bot Token 和 Chat ID 优先从 `~/.nanobot/config.json` 读取（已配置），
也可在 `.env` 中的 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 覆盖。

## 使用方法

### 在代码中调用

```python
from skills.telegram_notify.notify import TelegramNotifier

notifier = TelegramNotifier()

# 基础推送
await notifier.send("✅ 任务已完成！")

# 带标题的推送
await notifier.send_alert("文件监控告警", "data/ 目录新增 3 个可疑文件")

# 日报汇报
await notifier.send_report("今日日报", ["完成代码审查", "发现 2 个 Bug", "更新文档"])
```

### 让 Kylopro 调用此技能

直接对 Kylopro 说：
- "任务完成后发消息给我"
- "如果检测到异常请推送告警到 Telegram"
- "每天早上 9 点发一条日报给我"

## 技能说明书

**业务功能**：让 Kylopro 具备"主动汇报"能力，不再只是被动响应。

**核心库**：
- `httpx`：异步 HTTP 客户端，调用 Telegram Bot API（比 requests 更现代）

**概念沉淀**：掌握「Telegram Bot API」+ `httpx` 之后，你可以组合出：
- 任意服务异常时 Telegram 收警报（监控系统）
- 定时任务完成后自动汇报（报告机器人）
- Kylopro 主动询问你的下一步指令（反向控制循环）
- 多账号通知分发（群组 + 私聊同时推送）
