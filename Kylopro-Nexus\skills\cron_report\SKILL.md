---
name: cron_report
description: 定时汇报技能，按计划时间向 Telegram 推送日报、周报或自定义汇报
always: false
---

# 🌟 Kylopro 新技能：[晨报官 (Daily Herald)]

## ⚙️ 这个技能能做什么？

我会在你设定的时间，主动给你发一份"数字日报"——
不需要你问，我自己就会汇报：今天做了什么、系统状态怎样、有什么异常。

典型场景：
- 每天早上 9:00 发送系统心跳 + Ollama 状态
- 每天下班前 18:00 推送当日文件监控摘要
- 每周一发送上周异常汇总

## 🧩 协同实现的魔法库

- **APScheduler**：Python 定时任务调度器，轻量、无需操作系统任务计划
- **psutil**：采集 CPU/内存/磁盘等系统指标，心跳检测
- **telegram_notify**：定时把汇报推给你，永远准时

## 💡 指挥官，你学到了什么？

以后你看到任何"需要定期做的事"，都可以告诉我时间和内容，晨报官会替你盯着。
APScheduler + Telegram = 你的个人信息流，完全由你定义内容和频率。

## 使用方法

```python
from skills.cron_report.reporter import CronReporter

reporter = CronReporter()

# 每天 09:00 发晨报
reporter.add_daily_report(hour=9, minute=0)

# 每天 18:00 发晚报
reporter.add_daily_report(hour=18, minute=0, report_type="evening")

reporter.start()  # 阻塞运行
```
