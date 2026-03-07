---
name: skill_evolution
description: Kylopro 的自我进化引擎 — 自检技能、联网搜索、代码安全扫描、一键部署新技能
always: false
---

# 🌟 Kylopro 核心技能：[自我进化引擎 (Evolution Engine)]

## ⚙️ 这个技能能做什么？

这是 Kylopro 的"进化系统"，让她可以自主成长，而不是等你手动安装新功能。

**三大核心能力：**
1. **技能自检** — 开机或按需验证所有已装技能是否正常工作
2. **联网搜索** — 你说"我需要 X 功能"，她去 GitHub/PyPI 找相关项目，整理报告给你
3. **安全部署** — 你批准后，她自动：安全扫描代码 → 清理危险代码 → 部署到 `/skills` → 运行自检

## 🧩 协同实现的魔法库

- **httpx**：访问 GitHub Search API、PyPI（零额外依赖）
- **ast (Python 内置)**：静态分析代码 AST，检测危险导入和模式
- **importlib**：动态加载新技能模块（无需重启 Kylopro）
- **DeepSeek (deepseek-chat)**：只在"决策"时消耗 Token（评估搜索结果、生成技能说明书）

## 💡 指挥官，你学到了什么？

**这就是"协同进化准则"的执行引擎。**
- 所有新技能只能写入 `skills/` — core/ 永远不变（沙盒进化）
- 每个技能上线都有 SKILL.md（技能说明书）
- 安全扫描后才部署，你的确认是最后一道闸门

**Token 经济**：搜索和安全扫描走本地，只有"读懂搜索结果、生成说明书"才用 DeepSeek。

## 使用方法

```python
from skills.skill_evolution.verifier import SkillVerifier
from skills.skill_evolution.marketplace import SkillMarketplace

# 一键自检所有技能
verifier = SkillVerifier()
report = await verifier.run_all()

# 搜索新技能
market = SkillMarketplace()
results = await market.search("定时截图并识别文字")

# 批准并部署
await market.deploy(results[0], confirm=True)
```
