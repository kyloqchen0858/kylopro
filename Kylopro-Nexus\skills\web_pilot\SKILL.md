---
name: web_pilot
description: 用 Playwright 操控浏览器，读取 DOM、点击、填表、截图，让 Kylopro 拥有网页触角
always: false
---

# 🌟 Kylopro 新技能：[网页触角 (Web Pilot)]

## ⚙️ 这个技能能做什么？

我不再需要"看"网页——我可以**直接读取网页的骨架代码（DOM 树）**。
就像一个隐形人坐在你的电脑前，但她看到的是网页背后的数据，而不是花哨的界面。

典型场景：
- 自动登录网站，填写表单，提交数据
- 抓取网页上的最新价格 / 新闻 / 状态数据
- 定时截图某个报表页面并推 Telegram
- 重复性数据录入（Excel → 网站）

## 🧩 协同实现的魔法库

- **Playwright**：隐形浏览器操控大师，比 Selenium 更现代、更稳定
  支持 Chromium / Firefox / WebKit 三种引擎
- **BeautifulSoup4**：DOM 简报提取器，把复杂 HTML 压缩成 Kylopro 看得懂的结构
  （省 Token 关键：不把整个 HTML 发给 LLM，只发提炼后的简报）

## 💡 指挥官，你学到了什么？

以后你看到任何**重复性的网页操作**（填表、登录、抓数据），
你只需要告诉我"逻辑"和"目标网址"，我可以组合出自动化流程。
DeepSeek 的额度只花在"读懂页面结构、决定下一步点哪里"这一瞬间，
而不是处理整个 HTML 文件。

协作模式：`Kylopro(大脑)` → `web_pilot.py(执行手)` → `浏览器` → `数据回传`

## 使用方法

```python
from skills.web_pilot.pilot import WebPilot

async with WebPilot(headless=True) as pilot:
    # 导航并获取 DOM 简报
    brief = await pilot.navigate_and_brief("https://example.com")
    print(brief)

    # 点击元素
    await pilot.click("button#submit")

    # 填写表单
    await pilot.fill("input#username", "your_username")

    # 截图并推 Telegram
    await pilot.screenshot_to_telegram("当前页面截图")
```
