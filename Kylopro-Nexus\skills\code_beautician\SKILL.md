---
name: code_beautician
description: Kylopro 的代码美容师 — 扫描自身技能库，发现老化/冗余代码，用 deepseek-coder 生成优化建议并可选自动重写
always: false
---

# 🌟 Kylopro 新技能：[代码美容师 (Code Beautician)]

## ⚙️ 这个技能能做什么？

美容师是 Kylopro 的"自我审视"模块。
她定期扫描自己的 `skills/` 目录，就像程序员做代码 Review：

- 找出**过时的依赖**（哪个包有新版本了？）
- 找出**冗余技能**（某个 skill 被另一个技能完全覆盖了？）
- 找出**代码气味**（函数太长、注释缺失、异常未处理）
- 生成**优化建议报告**推 Telegram
- 可选**自动重写**（用 deepseek-coder，需要你二次确认）

## 🧩 协同实现的魔法库

- **ast**：本地语法分析，零 Token 找出代码结构问题
- **DeepSeek-coder**：只在"读完本地 AST 报告后决定怎么优化"时消耗 Token
- **pip + importlib**：本地检测依赖版本，不依赖网络

## 💡 指挥官，你学到了什么？

这是"自主进化"的完整闭环：
`感知(AST本地)` → `决策(deepseek-coder)` → `执行(重写skills/)` → `验证(skill_verifier自检)`

Token 经济原则：先本地 AST 分析，把"已经发现的问题"压缩成摘要，
只把**摘要**发给 deepseek-coder，而不是把整个文件发过去。
这样 1000 行代码只花 50 个 Token。

## 使用方法

```python
from skills.code_beautician.beautician import CodeBeautician

b = CodeBeautician()

# 全量扫描 + 报告推 Telegram
report = await b.run_full_audit()

# 只扫描单个技能
result = await b.audit_skill("file_monitor")

# 自动优化（需要 deepseek-coder + 用户确认）
await b.auto_fix("file_monitor", require_confirm=True)
```
