---
name: vision_rpa
description: 截取屏幕、OCR 识别文字、OpenCV 模板匹配坐标，PyAutoGUI 执行鼠标键盘操作
always: false
---

# 🌟 Kylopro 新技能：[全境飞行员 (Global Pilot)]

## ⚙️ 这个技能能做什么？

我将不再局限于处理文本文件或网页。
我可以**接管你的整个桌面**——看见屏幕、找到目标、移动鼠标、敲击键盘。
真正像一个坐在你桌前的数字助理，在你休息时替你盯着屏幕工作。

典型场景：
- 监控桌面，发现 Telegram 消息弹窗后截图发给你
- 定时截图某个应用窗口（股票、监控大屏），识别关键数字
- 把 Excel 里的数据一行行录入某个没有 API 的老旧系统
- 屏幕上出现"报警红灯"时立刻 Telegram 通知你

## 🧩 协同实现的魔法库

- **PyAutoGUI**：机械臂，模拟真实的鼠标移动和键盘输入
- **OpenCV**：电子眼，模板匹配——"在屏幕上找到这个图标在哪里"
- **EasyOCR / Tesseract**：文字识别，把截图里的数字和文字转成可处理的数据
- **Pillow (PIL)**：截图工具，抓取全屏或指定区域

## 💡 指挥官，你学到了什么？

省 Token 策略是关键：
- **截图 → 本地 OCR → 只传坐标/文字给 LLM**（不传高清图片，省 95% Token）
- 识别工作（找图标、读数字）全在本地完成——免费、快速
- DeepSeek 只做决策："这个数字超过阈值了吗？下一步该点哪里？"

这就是：`感知(本地)` + `决策(云端)` = `行动(本地)` 的完整闭环。

## 使用方法

```python
from skills.vision_rpa.vision import VisionRPA

rpa = VisionRPA()

# 找到屏幕上的图标并点击
await rpa.find_and_click("assets/telegram_icon.png")

# 截图识别文字
text = await rpa.screenshot_ocr(region=(0, 0, 800, 600))
print(text)

# 移动鼠标到坐标
rpa.move_to(500, 300)

# 键盘输入
rpa.type_text("Hello from Kylopro!")
```
