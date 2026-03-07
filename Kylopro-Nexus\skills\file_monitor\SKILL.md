---
name: file_monitor
description: 监控指定目录的文件变动，用 Ollama 本地生成摘要，异常时 Telegram 告警
always: false
---

# 🌟 Kylopro 新技能：[哨兵眼 (Sentinel Eye)]

## ⚙️ 这个技能能做什么？

我将成为你文件系统的不眠哨兵。当指定目录里有新文件出现、文件被修改或删除时，
我会第一时间在本地用 Ollama 分析内容，只把**摘要**发给你的 Telegram——
你的原始文件永远不会离开你的电脑。

典型场景：
- 监控 `Downloads/` 目录，有新文件时告诉你是什么
- 监控项目目录，代码文件修改时自动摘要 diff 内容
- 监控日志文件夹，出现 ERROR 关键词立即告警

## 🧩 协同实现的魔法库

- **watchdog**：文件系统事件监控，零 CPU 占用的事件驱动
- **Ollama (deepseek-r1:latest)**：本地大脑，在你电脑上分析文件内容，隐私绝对安全
- **telegram_notify**：只把摘要（几十个字）推给你，不传原文，省 Token

## 💡 指挥官，你学到了什么？

以后你看到任何"需要盯着某个文件夹"的场景，都可以告诉我让哨兵去盯。
核心思想：**本地感知 + 云端决策**。
- 感知（watchdog）和识别（Ollama OCR/摘要）在本地完成——免费、私密
- 只有"要不要告警"这个决定，才花你的 DeepSeek 额度

## 使用方法

```python
from skills.file_monitor.monitor import FileMonitor

# 监控下载目录
monitor = FileMonitor(
    watch_path="C:/Users/qianchen/Downloads",
    ollama_summarize=True,    # 用本地 Ollama 做摘要
    alert_on_delete=True,     # 删除事件也告警
)
await monitor.start()         # 阻塞运行，Ctrl+C 停止
```

或直接运行：
```powershell
python -m skills.file_monitor.monitor --path "C:/Users/qianchen/Downloads"
```
