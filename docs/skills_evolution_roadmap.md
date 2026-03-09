# Kylo 技能进化路线图

**版本**: v1.1 | **创建**: 2026-03-08 | **更新**: 2026-03-08 | **维护者**: Kylo（可自主更新此文件）  
**用途**: Kylo 主动阅读此文档，了解当前能力盲点与进化方向，按需推进技能部署。

---

## 使用说明（供 Kylo 读）

本文档是 **技能自进化的锚点**：
- **主动调阅时机**：接到新任务前、发现某类工具缺失时、每周例行 `cost_check` 后
- **更新方式**：完成某项进化后，将对应条目状态改为 `✅ 已落地`，并写上日期
- **升级优先级**：`🔴 阻塞` > `🟡 高价值` > `🟢 可选`

---

## 当前能力基线（2026-03-08）

| 类别 | 工具/方式 | 状态 |
|------|---------|------|
| **L0 本地脑** | `local_think` → Ollama | 📋 工具已就绪，需安装 Ollama + 拉取模型 |
| 主力搜索 | `tavily_search` | ✅ 已落地（月 1000 次免费） |
| 降级搜索 | `ddg_search` | ✅ 已落地（无限免费） |
| 精确抓取 | `web_fetch` | ✅ nanobot 原生 |
| 深度推理 | `deep_think` → deepseek-reasoner | ✅ 已落地 |
| 向量记忆 | `skills/kylobrain/vector_backend.py` + `WarmMemory.search()` | 🟡 已运行（向量后端可用，但主循环任务前直觉链路未全接通） |
| GUI 控制 | MCP / pyautogui | ⚠️ MCP 未配置 |
| 自托管搜索 | SearXNG | 📋 未部署（见 T1） |
| 邮件通道 | Email channel | ✅ nanobot 原生（需配置凭证） |
| 定时任务 | cron | ✅ nanobot 原生 |
| 财务监控 | `cost_check` / `cost_tracker.py` | ✅ 已落地 |

---

## 方案三：SearXNG 自托管元搜索引擎

> **优先级**: 🟡 高价值（部署后替代 DDG 成为永久免费 Tier-2，彻底摆脱第三方限制）

### 是什么

SearXNG 是开源自托管元搜索引擎，聚合 Google / Bing / Yahoo / DuckDuckGo / Startpage 等多引擎结果，**无追踪、无速率限制、完全本地运行**。用 Docker 5 分钟可部署。

- GitHub: https://github.com/searxng/searxng
- 文档: https://docs.searxng.org/
- 许可: AGPL-3.0（代码免费使用）

### 部署方法（Docker）

**前提**: Docker Desktop 已运行（`docker ps` 验证）

```bash
# 一行启动（开发测试用）
docker run -d \
  --name searxng \
  -p 8888:8080 \
  -e INSTANCE_NAME="Kylo-Search" \
  searxng/searxng:latest

# 验证
curl "http://localhost:8888/search?q=test&format=json"
```

**生产部署**（通过 docker-compose）：

```yaml
# docker-compose.yml 追加此段（在 services: 下）
searxng:
  image: searxng/searxng:latest
  container_name: searxng
  ports:
    - "8888:8080"
  volumes:
    - ./searxng:/etc/searxng:rw
  environment:
    - INSTANCE_NAME=Kylo-Search
    - AUTOCOMPLETE=duckduckgo
  restart: unless-stopped
  networks:
    - bot-network
```

**启动后验证**:
```bash
# 搜索测试
curl "http://localhost:8888/search?q=python+asyncio&format=json&language=zh-CN" | python -m json.tool | head -50
```

### API 接口规范

```
GET http://localhost:8888/search
参数:
  q       = 搜索词（必填）
  format  = json（固定）
  language= zh-CN / en-US（可选，默认 all）
  engines = google,bing,duckduckgo（可选，逗号分隔）
  time_range = day / week / month / year（可选）

返回结构:
{
  "results": [
    {
      "title": "...",
      "url": "...",
      "content": "...",  // 摘要
      "engine": "google",
      "score": 0.95
    }
  ],
  "number_of_results": 42
}
```

### 集成到 Kylopro 的步骤

1. **确认 Docker 运行**，执行上方一行启动命令
2. **在 `core/kylopro_tools.py` 新增 `SearXNGSearchTool`**：

```python
class SearXNGSearchTool(Tool):
    """本地 SearXNG 元搜索（零成本、无限次、多引擎聚合）"""

    name = "searxng_search"
    description = "通过本地 SearXNG 搜索网页（免费无限，需 Docker 运行）"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索词"},
            "language": {"type": "string", "default": "zh-CN"},
            "time_range": {"type": "string", "enum": ["", "day", "week", "month"], "default": ""}
        },
        "required": ["query"]
    }

    async def run(self, params: dict) -> str:
        import aiohttp, json
        base = "http://localhost:8888/search"
        p = {
            "q": params["query"],
            "format": "json",
            "language": params.get("language", "zh-CN"),
        }
        if params.get("time_range"):
            p["time_range"] = params["time_range"]
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(base, params=p, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        return f"SearXNG 返回 HTTP {r.status}，请确认 Docker 容器已启动"
                    data = await r.json()
            results = data.get("results", [])[:5]
            if not results:
                return "未找到相关结果"
            lines = [f"找到 {data.get('number_of_results', '?')} 条结果（显示前 5 条）:\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. [{r['title']}]({r['url']})")
                lines.append(f"   {r.get('content', '')[:200]}\n")
            return "\n".join(lines)
        except Exception as e:
            return f"SearXNG 不可用: {e}（退回 ddg_search）"
```

3. **在 `register_kylopro_tools` 中注册**：在现有 9 个工具后追加 `SearXNGSearchTool`
4. **更新 `skills/cost-manager/SKILL.md`**：搜索策略变为四级（SearXNG → Tavily → DDG → web_fetch）

### 新四级搜索策略（部署后）

```
0. SearXNG 可用（Docker 在线）? → searxng_search（本地零成本，最优先）
1. SearXNG 不可用 + Tavily 有额度? → tavily_search（高质量）
2. Tavily 耗尽? → ddg_search（免费）
3. 精确 URL? → web_fetch（零延迟）
```

---

## 近期技能进化清单

### T0 — 本地脑（Ollama）部署 ← 当前最高优先级

- **优先级**: 🔴 高价值（部署后约 30% 的云 API 调用可由本地零成本替代）
- **状态**: 📋 `local_think` 工具已就绪，仅需安装 Ollama 运行时
- **工具**: `local_think`（已在 `core/kylopro_tools.py` 实现，已注册）
- **路由规则**: `skills/local-brain/SKILL.md`（已创建）

**部署步骤**（用户执行一次即可）：

```bash
# 1. 下载安装（Windows 直接运行安装包）
# https://ollama.ai/download

# 2. 拉取代码生成模型
ollama pull qwen2.5-coder:7b

# 3. 验证运行（浏览器或 curl）
curl http://localhost:11434/api/tags
```

**Kylo 立即获得的 L0 能力**：
- 财务运算 → Python 精确执行，不走云 API
- 格式转换、日志统计、数据清洗 → 本地脚本
- 简单翻译、代码注释 → 本地对话
- 定时自动化报告 → 本地生成，不占预算

**四层大脑完整架构（部署后）**：
```
L0  local_think    → Ollama qwen2.5-coder:7b     ¥0/次   简单运算/脚本
L1  deepseek-chat  → cloud（当前会话）           ¥/token  对话/调度
L2  deep_think     → deepseek-reasoner           ¥¥/token 架构/根因
L3  minimax        → fallback on 429             ¥/token  限流保护
```

---

### T1 — SearXNG 集成（本文档已完整记录）

- **优先级**: 🟡 高价值
- **状态**: 📋 待部署
- **操作**: 确认 Docker 可用后，一行命令即可启动，再执行上方集成步骤
- **收益**: 彻底摆脱搜索 API 速率和配额限制，所有搜索永久免费

### T2 — 向量记忆激活

- **优先级**: 🟡 高价值
- **状态**: 🟡 依赖已安装，VectorBackend 已运行；剩余工作是把任务前 recall 完整并入主循环
- **操作**: 
  ```bash
  venv\Scripts\pip.exe install chromadb sentence-transformers
  ```
  当前运行态验证结果：
  - `WarmMemory.vector_status()` = `available=true, operational=true`
  - `WarmMemory.search()` 优先走向量检索，命中结果带 `_score`
  - `KyloConnector` 初始化日志显示 `vector=True`
  - 向量库目录：`brain/vector_store/`

  剩余差口：
  - `brain_hooks._build_brain_context()` 目前主要读取近期 `episodes/failures/patterns` 的 JSONL 概览
  - 默认主消息循环没有调用 `on_task_start() -> pre_task_intuition()`，所以“任务前语义 recall”还没完全进入每轮决策
- **收益**: 跨会话语义检索偏好/代码/决策记忆；失败模式可走向量召回

### T3 — MCP IDE 工具配置

- **优先级**: 🟡 高价值
- **状态**: 📋 待配置
- **操作**: 在 `config.json` 的 `mcp_servers` 中添加 filesystem MCP server
  ```json
  {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Users\\qianchen\\Desktop\\nanobot"]
  }
  ```
- **收益**: 直接操作文件系统不再需要 run_terminal 绕路

### T4 — 定时自检任务

- **优先级**: 🟢 可选
- **状态**: 📋 未配置
- **操作**: 在 nanobot `cron` 配置中添加每周日例行检查：
  - `cost_check` 财务报告
  - 读取此文档，评估哪些进化已可解锁
  - 如有上游更新（`docs/reports/`），摘要推送给用户
- **收益**: 自动维护，减少人工巡检

### T5 — GitHub Issues 同步

- **优先级**: 🟢 可选
- **状态**: 📋 需要 GitHub token
- **操作**: 向用户索取 GitHub token，写入 `data/local_config.json`，即可通过 `web_fetch` 调用 GitHub API
- **收益**: 直接读写项目 Issues，实现任务与代码仓库双向同步

### T6 — Brave Search 激活（可选 Tavily 替代）

- **优先级**: 🟢 可选（当前 Tavily 已够用）
- **状态**: 📋 需要 Brave key
- **说明**: nanobot 原生支持 `web_search` → Brave API，已有工具框架，只缺 key
- **操作**: 向用户索取 Brave API key，写入 config，即可用

---

### T7 — Cloud Sync 技能扩展（REST 平台桥）

- **优先级**: 🟡 高价值（已有可复用代码模板）
- **状态**: ✅ GitHub 同步已落地（2026-03-08）；平台扩展待进化
- **技能文档**: `skills/cloud-sync/SKILL.md`

**已落地**：
- GitHub REST API 文件同步（上传/更新/删除/增量 diff）
- 已验证：123 文件 / 删除 46 废旧文件 / 全量仓库同步

**进化子项**：

| 子项 | 目标 | 前置条件 | 优先级 |
|------|------|---------|--------|
| **T7-F1** GitHub Issues 双向同步 | DEVLOG TODO ↔ GitHub Issue，自动开/关 | token 已有 | 🟡 高价值 |
| **T7-F2** Notion 项目看板同步 | tasks/ ↔ Notion Database 双向同步 | Notion Integration token | 🟡 按需 |
| **T7-F3** Freelancer 项目发布助手 | 从任务需求自动起草并发布项目 | Freelancer Developer token | 🟢 按需 |
| **T7-F4** 上游仓库自动 diff 监控 | 自动对比本地 vs jjleng/nanobot upstream | 无（token 已有）| 🟡 替代手动巡检 |

**T7-F1 解锁操作**（主人说"开始做 Issues 同步"时）：

```python
# 从 DEVLOG.md 中提取 Phase TODO → 创建 GitHub Issue
POST https://api.github.com/repos/kyloqchen0858/kylopro/issues
{"title": "Phase 11: ...", "body": "...", "labels": ["enhancement"]}

# 查询已有 Issues 避免重复
GET https://api.github.com/repos/kyloqchen0858/kylopro/issues?state=all&per_page=100
```

**T7-F3 Freelancer 接入前置**（一次性）：
1. 主人访问 https://developers.freelancer.com/console → 创建 App → 获取 Developer token
2. 写入 `data/local_config.json` 的 `freelancer_token` 字段
3. Kylo 即可调用 `POST /api/projects/0.1/projects/` 创建项目

---

## 技能自进化操作规范

Kylo 在以下情况下应**主动阅读此文档**：
- 用户要求某功能但当前工具无法满足
- 执行 `cost_check` 发现预算异常（考虑降级路线）
- 完成某项进化后（更新此文档状态）
- 每周例行检查时

### 自主更新此文档的方式

```python
# 完成某项进化后，用 write_file 更新对应行的状态：
# 将 "📋 待部署" → "✅ 已落地（2026-03-XX）"
# 将 "⚠️ 依赖未安装" → "🟡 已运行（向量后端在线，待接主循环 recall）"
```

---

## 长期方向（2026 H2）

| 方向 | 说明 | 前置条件 |
|------|------|---------|
| 本地 LLM 推理 | Ollama + qwen2.5 作为离线 L0 层，零成本 | 本机显卡 >= 8GB VRAM |
| 浏览器自动化 | Playwright MCP 替代 pyautogui，更稳定 | `npm install @playwright/mcp` |
| 知识库 RAG | 向量库 + 长文档切片，支持代码库问答 | T2 向量记忆完成后扩展 |
| 多智能体协作 | 多个 nanobot SubAgent 并行，通过 TaskBridge 协同 | TaskBridge 稳定运行 |
| 自动测试生成 | 读取代码 → 生成 pytest → 自动运行 → 汇报覆盖率 | Python toolchain ok |

---

*此文档由 Kylo / GitHub Copilot 共同维护，鼓励 Kylo 在完成进化后自主更新状态字段。*
