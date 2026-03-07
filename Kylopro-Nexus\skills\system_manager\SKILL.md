---
name: system_manager
description: 管理 Windows 软件生命周期，扫描冗余软件并安全卸载，使用 winget + PowerShell
always: false
---

# 🌟 Kylopro 新技能：[数字管家 (System Steward)]

## ⚙️ 这个技能能做什么？

有了 Kylopro 之后，很多工具就变得多余了——
她帮你列出这些软件，告诉你"为什么它现在可以卸载"，然后**等你确认后**再动手。

典型场景：
- 扫描 Antigravity / Trae / Copilot 等 AI 工具，评估是否还需要
- 卸载自己不再用的软件（带二次确认，绝不静默删除）
- 查看磁盘空间被哪些软件占用最多
- 搜索 + 安装新工具（winget install）

## 🧩 协同实现的魔法库

- **winget**：Windows 官方包管理器，可列表/搜索/安装/卸载
- **PowerShell WMI**：`Get-Package` / `Get-CimInstance Win32_Product` 补充查询
- **psutil**：磁盘占用、进程状态分析

## 💡 指挥官，你学到了什么？

Kylopro 是你的软件替代品——不是工具收集者，而是工具精简者。
她会主动问你："这个软件你现在还需要吗？" 因为她自己就能做那件事。

安全原则：**扫描免费，卸载需确认**。任何删除操作都会要求你输入 'YES' 二次确认。

## 使用方法

```python
from skills.system_manager.manager import SystemManager

mgr = SystemManager()

# 列出所有已装软件（按大小排序）
apps = await mgr.list_installed()

# 找出 Kylopro 可以替代的软件
redundant = await mgr.find_redundant_apps()

# 安全卸载（有二次确认）
await mgr.uninstall("Trae", require_confirm=True)

# 搜索可用软件
results = await mgr.search("playwright")
```

## 可替代软件建议

| 软件 | Kylopro 替代能力 | 建议 |
|------|------------|------|
| Antigravity IDE | IDE Bridge + 文件操作 + DeepSeek | 视需要保留 |
| Trae IDE | IDE Bridge + Playwright + vision_rpa | 视需要保留 |
| 各类截图工具 | vision_rpa.screenshot | 可替代 |
| 定时提醒软件 | cron_report | 可替代 |
