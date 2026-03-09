---
name: feishu-writer
description: "AI 公众号文章自动生成：搜索 AI 技术热点 → 生成微信公众号风格文章 → 写入飞书文档供审阅"
metadata: {"nanobot":{"always":false}}
---

# feishu-writer — AI公众号文章自动写作技能

## 技能描述

Kylo 的主动生产技能。完整工作流：
1. 使用 `web_search` + `web_fetch` 抓取最新 AI 技术热点资讯
2. 按微信公众号文章标准写作（结构清晰、有观点、有温度）
3. 调用 `feishu(action="create_doc")` 写入飞书文档
4. 发送飞书消息通知用户审阅

执行前先做失败记忆预检：
- `kylobrain(action="recall", query="feishu create_doc", collection="failures")`
- 若命中历史失败，先执行最小验证：`feishu(action="status")` -> `oauth2_vault(action="get_token")`

**触发方式**：用户说「帮我写 AI 周报」「生成公众号文章」「抓取 AI 热点写飞书」等

## 工作流步骤

### Step 1 — 搜索 AI 热点（2-3 次搜索）

```
web_search(query="AI 人工智能 最新技术突破 2026 本周")
web_search(query="LLM 大模型 最新进展 2026")
web_search(query="AI Agent 多智能体 最新动态 2026")
```

搜索要点：
- 优先搜索近 7 天的内容（加上当前日期）
- 聚焦：大模型新发布、重要论文、产品发布、行业动态
- 如有 Tavily API，优先用 `tavily_search`；否则用 `duckduckgo_search`

### Step 2 — 深度获取关键文章

对搜索结果中最有价值的 2-3 篇文章：
```
web_fetch(url="...", extract_text=true)
```

### Step 3 — 生成公众号文章

**写作规范**（微信公众号风格）：

```
# 文章标题（吸引眼球，不超过20字）

文章副标题或导语（1-2句，点明核心价值）

---

## 一、本周最大事件：[事件名]

[300-500字，用故事化叙述，有数据支撑]

## 二、值得关注的进展

### 1. [小标题]
[100-200字，简明扼要]

### 2. [小标题]
[100-200字]

## 三、Kylo 的思考

[100-200字，结合当前 AI 发展趋势的主观判断/观点]
这部分要有温度，有观点，不是纯罗列信息。

---

**本文由 Kylo 自动生成 · 已写入飞书供审阅**
```

**写作要求**：
- 语气：专业但不学术，有温度有观点
- 深度：不只是新闻摘要，要有分析和判断
- 字数：正文 800-1500 字
- 结构：清晰分节，每节都有小标题
- 真实：只写能从搜索结果中支撑的内容，不编造数据

### Step 4 — 写入飞书文档

```json
{
  "tool": "feishu",
  "action": "create_doc",
  "title": "AI技术周报 [日期]",
  "content": "[生成的 Markdown 文章]",
  "notify": true
}
```

### Step 5 — 向用户报告

向用户（Telegram）报告：
- 文章标题和主要话题
- 飞书文档 URL（供访问）
- 3句话摘要本周最大进展

## 执行完成后

- 调用 `kylobrain(action="post_task")` 记录本次任务结果
- 写一条记忆：本次搜索的质量/哪些关键词效果好
- 若失败：调用 `kylobrain(action="record_failure", error_type="feishu_writer", task="...", fix="...")`

## 处理异常

| 情况 | 处理方式 |
|------|---------|
| 飞书未配置 | 回复「请先配置飞书：发送 /setup_feishu」，把文章以 Telegram 消息形式发送 |
| 搜索无结果 | 换关键词重试，最多 3 次，仍然失败则报告 |
| 网络超时 | 跳过该文章，继续处理其他来源 |
| 文章太短（<400字）| 继续搜索补充，或告知用户本次素材有限 |

## 进阶：定期自动发布

可通过 `cron` 工具设置定期触发：
```json
{
  "tool": "cron",
  "schedule": "每周一 09:00",
  "action": "feishu-writer:generate_weekly"
}
```

## 输出样本（实际生成内容保密，仅示意结构）

```
📄 已完成：AI技术周报 2026-03-09

主要话题：
- GPT-5 发布传闻升温，OpenAI 确认 Q2 计划
- Google Gemini Ultra 2.0 多模态基准刷新
- 开源 DeepSeek-V3 推理速度提高 40%

飞书文档：https://xxxx.feishu.cn/document/xxxxx
（点击链接审阅后，回复「发布」即可）
```
