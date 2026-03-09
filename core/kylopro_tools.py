"""
Kylopro 自定义工具 — 作为 nanobot Tool 子类实现
注册到 nanobot AgentLoop.tools 即可使用
"""

import asyncio
import base64
import io
import json
import subprocess
from pathlib import Path
from typing import Any
from datetime import datetime

from nanobot.agent.tools.base import Tool

from kylo_tools.task_bridge import TaskBridge
from core.cost_tracker import get_tracker, CostTracker


class TaskInboxTool(Tool):
    """任务收件箱：查看/添加/完成 tasks/ 目录下的 Markdown 任务"""

    def __init__(self, workspace: Path):
        self._tasks_dir = workspace / "tasks"
        self._done_dir = self._tasks_dir / "done"
        self._tasks_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "task_inbox"

    @property
    def description(self) -> str:
        return "管理任务收件箱：list 查看待处理任务 / add 添加新任务 / complete 标记任务完成"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "add", "complete"],
                    "description": "操作类型"
                },
                "title": {
                    "type": "string",
                    "description": "任务标题（add 时必填）"
                },
                "content": {
                    "type": "string",
                    "description": "任务详细内容（add 时可选）或任务文件名（complete 时必填）"
                },
                "priority": {
                    "type": "string",
                    "enum": ["P0", "P1", "P2", "P3"],
                    "description": "任务优先级（add 时可选，默认 P1）"
                }
            },
            "required": ["action"]
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        if action == "list":
            return self._list_tasks()
        elif action == "add":
            return self._add_task(
                title=kwargs.get("title", "未命名任务"),
                content=kwargs.get("content", ""),
                priority=kwargs.get("priority", "P1"),
            )
        elif action == "complete":
            return self._complete_task(kwargs.get("content", ""))
        return f"未知操作: {action}"

    def _list_tasks(self) -> str:
        tasks = sorted(self._tasks_dir.glob("*.md"))
        if not tasks:
            return "📭 收件箱为空"
        lines = ["📬 待处理任务:"]
        for t in tasks:
            lines.append(f"  • {t.name}")
        return "\n".join(lines)

    def _add_task(self, title: str, content: str, priority: str) -> str:
        now = datetime.now().strftime("%Y%m%d_%H%M")
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)[:50].strip()
        filename = f"{now}_{safe_title}.md"
        filepath = self._tasks_dir / filename
        body = f"# {title}\n\n## 优先级\n{priority}\n\n## 描述\n{content or '（待补充）'}\n"
        filepath.write_text(body, encoding="utf-8")
        return f"✅ 已添加任务: {filename}"

    def _complete_task(self, filename: str) -> str:
        if not filename:
            return "错误: 需要提供任务文件名"
        src = self._tasks_dir / filename
        if not src.exists():
            return f"错误: 任务文件不存在: {filename}"
        self._done_dir.mkdir(parents=True, exist_ok=True)
        src.rename(self._done_dir / filename)
        return f"✅ 已完成任务: {filename}"


class DeepThinkTool(Tool):
    """触发深度推理 — 临时切换到高级推理模型处理复杂问题"""

    def __init__(self, provider, default_model: str = "deepseek/deepseek-reasoner"):
        self._provider = provider
        self._model = default_model

    @property
    def name(self) -> str:
        return "deep_think"

    @property
    def description(self) -> str:
        return "对复杂问题进行深度推理分析。适用于：架构设计、bug 根因分析、多步骤规划、代码审计等需要深度思考的场景。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "需要深度思考的问题或分析请求"
                },
                "context": {
                    "type": "string",
                    "description": "相关上下文信息（代码片段、错误日志等）"
                }
            },
            "required": ["question"]
        }

    async def execute(self, **kwargs: Any) -> str:
        question = kwargs["question"]
        context = kwargs.get("context", "")

        prompt = f"请深度分析以下问题：\n\n{question}"
        if context:
            prompt += f"\n\n相关上下文：\n{context}"

        try:
            messages = [
                {"role": "system", "content": "你是一个深度分析专家。请进行系统性的思考和推理。"},
                {"role": "user", "content": prompt},
            ]
            response = await self._provider.chat(
                messages=messages,
                model=self._model,
                temperature=0.0,
                max_tokens=4096,
            )
            content = response.get("content", "") if isinstance(response, dict) else str(response)
            return f"🧠 深度分析结果:\n\n{content}"
        except Exception as e:
            return f"深度思考失败 ({self._model}): {e}\n\n请直接用当前模型分析问题。"


class TaskReadTool(Tool):
    """读取共享任务状态文件。"""

    def __init__(self, bridge: TaskBridge):
        self._bridge = bridge

    @property
    def name(self) -> str:
        return "task_read"

    @property
    def description(self) -> str:
        return "读取 tasks/active_task.json 中的当前任务状态。适用于查询后台任务进度、状态和中断标记。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["summary", "json"],
                    "description": "返回摘要文本或完整 JSON。默认 summary。"
                }
            }
        }

    async def execute(self, **kwargs: Any) -> str:
        state = self._bridge.read_state()
        return self._bridge.format_state(state, mode=kwargs.get("format", "summary"))


class TaskWriteTool(Tool):
    """更新共享任务状态文件。"""

    def __init__(self, bridge: TaskBridge):
        self._bridge = bridge

    @property
    def name(self) -> str:
        return "task_write"

    @property
    def description(self) -> str:
        return "写入或更新 tasks/active_task.json。适用于登记长任务、推进进度、记录摘要、写入防死循环限制。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "任务 ID"},
                "title": {"type": "string", "description": "任务标题"},
                "status": {
                    "type": "string",
                    "enum": ["idle", "queued", "running", "waiting", "completed", "failed", "interrupted"],
                    "description": "任务状态"
                },
                "owner": {"type": "string", "description": "任务归属，例如 main / subagent"},
                "progress": {"type": "integer", "minimum": 0, "maximum": 100, "description": "任务进度百分比"},
                "current_step": {"type": "string", "description": "当前步骤"},
                "summary": {"type": "string", "description": "任务摘要"},
                "detail": {"type": "string", "description": "详细说明"},
                "max_iterations": {"type": "integer", "minimum": 0, "description": "最大迭代数"},
                "max_runtime_seconds": {"type": "integer", "minimum": 0, "description": "最大运行时长（秒）"},
                "append_history": {"type": "string", "description": "追加一条历史记录"},
                "metadata_json": {"type": "string", "description": "附加元数据 JSON 字符串"},
                "clear_interrupt": {"type": "boolean", "description": "是否清除中断标记"},
                "reset": {"type": "boolean", "description": "是否重置为全新状态后再写入"},
                "format": {
                    "type": "string",
                    "enum": ["summary", "json"],
                    "description": "返回摘要文本或完整 JSON。默认 summary。"
                }
            }
        }

    async def execute(self, **kwargs: Any) -> str:
        metadata = None
        metadata_json = kwargs.get("metadata_json")
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError as exc:
                return f"Error: metadata_json must be valid JSON: {exc}"

        state = self._bridge.write_state(
            task_id=kwargs.get("task_id"),
            title=kwargs.get("title"),
            status=kwargs.get("status"),
            owner=kwargs.get("owner"),
            progress=kwargs.get("progress"),
            current_step=kwargs.get("current_step"),
            summary=kwargs.get("summary"),
            detail=kwargs.get("detail"),
            max_iterations=kwargs.get("max_iterations"),
            max_runtime_seconds=kwargs.get("max_runtime_seconds"),
            metadata=metadata,
            append_history=kwargs.get("append_history"),
            clear_interrupt=kwargs.get("clear_interrupt", False),
            reset=kwargs.get("reset", False),
        )
        return self._bridge.format_state(state, mode=kwargs.get("format", "summary"))


class TaskInterruptTool(Tool):
    """给当前任务写入中断标记。"""

    def __init__(self, bridge: TaskBridge):
        self._bridge = bridge

    @property
    def name(self) -> str:
        return "task_interrupt"

    @property
    def description(self) -> str:
        return "为 tasks/active_task.json 写入 interrupt_requested=true。用于用户要求停止、取消或暂停长任务时。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "中断原因说明"
                },
                "format": {
                    "type": "string",
                    "enum": ["summary", "json"],
                    "description": "返回摘要文本或完整 JSON。默认 summary。"
                }
            }
        }

    async def execute(self, **kwargs: Any) -> str:
        state = self._bridge.interrupt(reason=kwargs.get("reason"))
        return self._bridge.format_state(state, mode=kwargs.get("format", "summary"))


# ═══════════════════════════════════════════════════════════════════
# 搜索工具：Tavily（主力）→ DuckDuckGo（免费 fallback）
# ═══════════════════════════════════════════════════════════════════

def _load_tavily_key(workspace: Path) -> str:
    """从 data/local_config.json 读取 Tavily key。"""
    cfg_file = workspace / "data" / "local_config.json"
    if cfg_file.exists():
        try:
            return json.loads(cfg_file.read_text(encoding="utf-8")).get("tavily_api_key", "")
        except Exception:
            pass
    return ""


class TavilySearchTool(Tool):
    """Tavily 智能搜索——专为 AI Agent 优化，直接返回提炼后的网页内容。
    
    主力搜索工具，每月 1000 次免费额度。额度耗尽时请改用 ddg_search。
    调用前会自动检查剩余配额，耗尽时直接返回提示。
    """

    def __init__(self, tracker: CostTracker, workspace: Path):
        self._tracker = tracker
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "tavily_search"

    @property
    def description(self) -> str:
        return (
            "用 Tavily 搜索网页，返回提炼后的高质量内容摘要（专为 AI Agent 优化）。"
            "每月 1000 次免费，调用 cost_check 可查剩余次数。额度耗尽时改用 ddg_search。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词或问题"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量（默认 5，最多 10）",
                    "minimum": 1,
                    "maximum": 10,
                },
                "search_depth": {
                    "type": "string",
                    "enum": ["basic", "advanced"],
                    "description": "basic=1 credit（默认），advanced=2 credits（更深度）"
                },
                "include_answer": {
                    "type": "boolean",
                    "description": "是否包含 Tavily 的综合回答（默认 true）"
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"]
        max_results = min(int(kwargs.get("max_results", 5)), 10)
        search_depth = kwargs.get("search_depth", "basic")
        include_answer = kwargs.get("include_answer", True)
        credits_needed = 2 if search_depth == "advanced" else 1

        # 配额检查
        remaining = self._tracker.tavily_remaining()
        if remaining < credits_needed:
            return (
                f"⚠️ Tavily 本月免费额度已耗尽（剩余 {remaining} credits，需要 {credits_needed}）。\n"
                f"请改用 ddg_search 工具进行免费搜索。"
            )

        api_key = _load_tavily_key(self._workspace)
        if not api_key:
            return "❌ Tavily API key 未配置（data/local_config.json → tavily_api_key）"

        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                    include_answer=include_answer,
                ),
            )

            self._tracker.record_tavily_call(credits=credits_needed)

            lines = [f"🔍 Tavily 搜索：{query}（剩余 {remaining - credits_needed} credits）\n"]
            if include_answer and result.get("answer"):
                lines.append(f"**综合回答**: {result['answer']}\n")

            for i, r in enumerate(result.get("results", []), 1):
                lines.append(
                    f"[{i}] {r.get('title', '无标题')}\n"
                    f"    URL: {r.get('url', '')}\n"
                    f"    {r.get('content', '')[:300]}\n"
                )

            return "\n".join(lines)

        except Exception as e:
            return f"Tavily 搜索失败: {e}\n建议改用 ddg_search 工具。"


class DuckDuckGoSearchTool(Tool):
    """DuckDuckGo 免费搜索——无 API Key、无限额度、永久免费。
    
    Tavily 额度耗尽后的 fallback 方案，或在不需要深度内容摘要时使用。
    高频使用时可能遇到 IP 临时限速（通常 1 分钟后恢复）。
    """

    def __init__(self, tracker: CostTracker):
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "ddg_search"

    @property
    def description(self) -> str:
        return (
            "用 DuckDuckGo 免费搜索网页（无 API key，无使用限额）。"
            "Tavily 额度耗尽时的 fallback，或日常轻量搜索。"
            "返回标题、URL 和摘要片段（不含深度内容）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词"
                },
                "max_results": {
                    "type": "integer",
                    "description": "返回结果数量（默认 8，最多 20）",
                    "minimum": 1,
                    "maximum": 20,
                },
                "region": {
                    "type": "string",
                    "description": "搜索地区（默认 cn-zh 中文结果，可选 wt-wt 全球）",
                    "default": "cn-zh",
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"]
        max_results = min(int(kwargs.get("max_results", 8)), 20)
        region = kwargs.get("region", "cn-zh")

        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()

            def _search():
                with DDGS() as ddgs:
                    return list(ddgs.text(query, region=region, max_results=max_results))

            results = await loop.run_in_executor(None, _search)
            self._tracker.record_ddg_call()

            if not results:
                return f"🦆 DuckDuckGo 未找到结果：{query}"

            lines = [f"🦆 DuckDuckGo 搜索：{query}（{len(results)} 条结果）\n"]
            for i, r in enumerate(results, 1):
                lines.append(
                    f"[{i}] {r.get('title', '无标题')}\n"
                    f"    URL: {r.get('href', '')}\n"
                    f"    {r.get('body', '')[:250]}\n"
                )
            return "\n".join(lines)

        except Exception as e:
            return (
                f"DuckDuckGo 搜索失败（可能是 IP 限速）: {e}\n"
                f"建议等待 1 分钟后重试，或使用 web_fetch 直接抓取指定 URL。"
            )


# ═══════════════════════════════════════════════════════════════════
# 财务工具：查询预算 / 设置限额
# ═══════════════════════════════════════════════════════════════════

class CostCheckTool(Tool):
    """查看当前财务状态：Tavily 剩余配额、本周预算余额、模型费用明细。"""

    def __init__(self, tracker: CostTracker):
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "cost_check"

    @property
    def description(self) -> str:
        return (
            "查看 Kylopro 当前财务状态：Tavily 剩余搜索次数、本周人民币预算余额、"
            "各模型 token 费用明细。决策前先调用此工具评估成本。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["summary", "json"],
                    "description": "返回摘要（默认）或完整 JSON",
                },
            },
        }

    async def execute(self, **kwargs: Any) -> str:
        fmt = kwargs.get("format", "summary")
        if fmt == "json":
            return json.dumps(self._tracker.get_state(), ensure_ascii=False, indent=2)
        return self._tracker.summary()


class SetWeeklyBudgetTool(Tool):
    """设置每周人民币预算限额。 Kylo 将根据此限额决策是否使用付费 API。"""

    def __init__(self, tracker: CostTracker):
        self._tracker = tracker

    @property
    def name(self) -> str:
        return "set_weekly_budget"

    @property
    def description(self) -> str:
        return "设置本周人民币预算上限。达到暂停阈值（5%）时，Kylo 会自动切换到免费工具。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "weekly_budget_rmb": {
                    "type": "number",
                    "description": "每周预算（人民币），如 20 表示每周 20 元",
                    "minimum": 0,
                },
            },
            "required": ["weekly_budget_rmb"],
        }

    async def execute(self, **kwargs: Any) -> str:
        budget = float(kwargs["weekly_budget_rmb"])
        self._tracker.set_weekly_budget(budget)
        return (
            f"✅ 每周预算已设为 ¥{budget:.2f}\n"
            f"当前余额: ¥{self._tracker.weekly_remaining():.4f}\n"
            f"预警阈值: 剩余 20% 时提示，剩余 5% 时停止非关键付费 API"
        )


# ═══════════════════════════════════════════════════════════════════
# L0 本地脑：Ollama 三模型精细路由
#   chat     → qwen2.5:7b      通用对话/文本分析/摘要/翻译
#   run_code → deepseek-coder-v2:16b  代码生成 + subprocess 执行
#   reason   → deepseek-r1:latest    链式推理/财务分析/多步规划
# ═══════════════════════════════════════════════════════════════════

# 三模型默认映射（用户已安装）
_LOCAL_MODELS = {
    "chat":     "qwen2.5:7b",           # 4.7GB — 通用，快速
    "run_code": "deepseek-coder-v2:16b", # 8.9GB — 代码生成首选
    "reason":   "deepseek-r1:latest",    # 5.2GB — 链式推理 (CoT)
}


class LocalThinkTool(Tool):
    """L0 本地脑 — 零 API 成本调用本地 Ollama 模型。

    三种模式对应三个专用模型：
      chat     → qwen2.5:7b          通用对话、文本分析、翻译、摘要
      run_code → deepseek-coder-v2:16b  生成 Python 代码并 subprocess 自动执行
      reason   → deepseek-r1:latest    链式推理（CoT）、财务分析、多步规划

    Ollama 未运行时返回明确安装提示，不影响云 API 工具正常使用。
    """

    OLLAMA_URL = "http://localhost:11434"

    def __init__(self, workspace: Path):
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "local_think"

    @property
    def description(self) -> str:
        return (
            "调用本地 Ollama 模型（零 API 成本）。"
            "三种模式：chat=通用对话(qwen2.5:7b)，"
            "run_code=生成并执行Python代码(deepseek-coder-v2:16b)，"
            "reason=链式推理/财务分析(deepseek-r1:latest)。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "发给本地模型的请求或问题"
                },
                "mode": {
                    "type": "string",
                    "enum": ["chat", "run_code", "reason"],
                    "description": (
                        "chat=通用对话返回文本(qwen2.5:7b)；"
                        "run_code=生成Python代码并自动执行(deepseek-coder-v2:16b)；"
                        "reason=链式推理分析(deepseek-r1:latest)"
                    ),
                },
                "model": {
                    "type": "string",
                    "description": "覆盖默认模型（不指定则按 mode 自动选择）",
                },
                "context": {
                    "type": "string",
                    "description": "附加上下文（财务数据、代码片段、日志等）",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, **kwargs: Any) -> str:
        import re
        import subprocess
        import sys

        prompt = kwargs["prompt"]
        mode = kwargs.get("mode", "chat")
        context = kwargs.get("context", "")

        # 按 mode 自动选择模型，可被 model 参数覆盖
        model = kwargs.get("model") or _LOCAL_MODELS.get(mode, "qwen2.5:7b")

        # 构建 prompt
        full_prompt = f"{prompt}\n\n相关上下文:\n{context}" if context else prompt

        if mode == "run_code":
            sys_prompt = (
                "你是一个 Python 脚本生成器。"
                "只输出一个可运行的 Python 代码块（```python ... ```），不要有任何解释。"
            )
        elif mode == "reason":
            sys_prompt = (
                "你是一个逻辑分析专家。请用分步推理（Step-by-step）回答，"
                "每步标注推理依据，最终给出明确结论。"
            )
        else:
            sys_prompt = "你是 Kylo 的本地助手，用中文简洁回答问题。"

        # 调用 Ollama /api/chat（支持多轮格式）
        try:
            import aiohttp

            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 4096},
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.OLLAMA_URL}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 404:
                        return (
                            f"⚠️ 模型 `{model}` 未找到。\n"
                            f"运行: ollama pull {model}"
                        )
                    if resp.status != 200:
                        err = await resp.text()
                        return f"Ollama 返回错误 {resp.status}: {err[:300]}"
                    data = await resp.json()
                    response_text = (data.get("message", {}).get("content") or "").strip()

        except (OSError, ConnectionRefusedError):
            return (
                "⚠️ 本地 Ollama 服务未运行。\n"
                "  安装: https://ollama.ai/download\n"
                f"  拉取: ollama pull {model}\n"
                "  启动: ollama serve"
            )
        except Exception as e:
            if "connect" in str(e).lower() or "refused" in str(e).lower():
                return f"⚠️ Ollama 未运行。启动: ollama serve"
            return f"local_think 调用失败: {e}"

        # chat / reason 模式：直接返回
        if mode != "run_code":
            tag = "💭" if mode == "reason" else "🤖"
            return f"{tag} [本地 {model}]\n\n{response_text}"

        # run_code 模式：提取代码块并用 subprocess 执行
        code_blocks = re.findall(r"```(?:python)?\n?(.*?)```", response_text, re.DOTALL)
        if not code_blocks:
            code = response_text.strip()
            if not code.startswith(("import", "from", "#", "def ", "class ", "print", "result")):
                return (
                    f"🤖 模型未生成标准代码块，原始回复:\n{response_text[:600]}\n\n"
                    "提示：改用 mode=chat 查看原始输出，或细化 prompt 要求输出代码。"
                )
        else:
            code = code_blocks[0].strip()

        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self._workspace),
            )
            if result.returncode != 0 and result.stderr:
                return (
                    f"🤖 [本地 {model}] 代码执行失败:\n"
                    f"```\n{result.stderr.strip()[:500]}\n```\n"
                    f"生成的代码:\n```python\n{code[:400]}\n```"
                )
            output = result.stdout.strip() or "(代码执行完成，无输出)"
            return f"🤖 [本地 {model}] 执行结果:\n{output}"

        except subprocess.TimeoutExpired:
            return f"⚠️ 代码执行超时（30s）:\n```python\n{code[:300]}\n```"
        except Exception as e:
            return f"代码执行异常: {e}"


# ─────────────────────────────────────────────────────────────
# 屏幕操作工具
# ─────────────────────────────────────────────────────────────

class ScreenTool(Tool):
    """
    屏幕操作工具：截图、鼠标点击/移动/滚动、键盘输入、窗口列表。

    action 参数决定操作类型：
      - screenshot  : 截取屏幕，返回 base64 PNG + 分辨率信息
      - click       : 鼠标左键点击 (x, y)
      - right_click : 鼠标右键点击 (x, y)
      - double_click: 双击 (x, y)
      - move        : 移动鼠标到 (x, y)
      - scroll      : 在 (x, y) 处滚动，clicks 为滚动格数（负=向下）
      - type        : 输入文字（text 参数）
      - hotkey      : 发送快捷键组合，如 "ctrl,c"、"alt,F4"
      - press       : 按下单个按键，如 "enter"、"esc"、"tab"
      - windows     : 列出当前所有可见窗口标题
      - focus_window: 激活指定标题的窗口（title 参数，支持模糊匹配）
    """

    name = "screen"
    description = (
        "屏幕操作工具：screenshot截图/click点击/type输入/hotkey快捷键/press按键/"
        "windows窗口列表/focus_window激活窗口。用于 GUI 自动化和屏幕读取。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["screenshot", "click", "right_click", "double_click",
                         "move", "scroll", "type", "hotkey", "press",
                         "windows", "focus_window"],
                "description": "操作类型",
            },
            "x": {"type": "integer", "description": "鼠标 X 坐标（像素）"},
            "y": {"type": "integer", "description": "鼠标 Y 坐标（像素）"},
            "text": {"type": "string", "description": "type 操作时输入的文字"},
            "keys": {"type": "string", "description": "hotkey: 逗号分隔的按键，如 'ctrl,c'"},
            "key": {"type": "string", "description": "press: 单个按键名称"},
            "clicks": {"type": "integer", "description": "scroll: 滚动格数，负数=向下，默认-3"},
            "title": {"type": "string", "description": "focus_window: 窗口标题关键词"},
            "region": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "screenshot 可选截取区域 [x, y, width, height]",
            },
        },
        "required": ["action"],
    }

    async def execute(self, **kwargs: Any) -> str:
        return await self.run(**kwargs)

    async def run(self, action: str, x: int = 0, y: int = 0,
                  text: str = "", keys: str = "", key: str = "",
                  clicks: int = -3, title: str = "",
                  region: list | None = None) -> str:
        try:
            import pyautogui
            import mss
            from PIL import Image
            pyautogui.FAILSAFE = True   # 移到左上角触发紧急停止
            pyautogui.PAUSE = 0.05
        except ImportError:
            return "❌ 屏幕工具未安装，请运行：pip install pyautogui mss Pillow"

        if action == "screenshot":
            with mss.mss() as sct:
                if region and len(region) == 4:
                    mon = {"left": region[0], "top": region[1],
                           "width": region[2], "height": region[3]}
                else:
                    mon = sct.monitors[1]  # 主显示器
                img = sct.grab(mon)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode()
            return (
                f"📸 截图完成 {pil_img.width}×{pil_img.height}px\n"
                f"data:image/png;base64,{b64}"
            )

        elif action == "click":
            pyautogui.click(x, y)
            return f"✅ 左键点击 ({x}, {y})"

        elif action == "right_click":
            pyautogui.rightClick(x, y)
            return f"✅ 右键点击 ({x}, {y})"

        elif action == "double_click":
            pyautogui.doubleClick(x, y)
            return f"✅ 双击 ({x}, {y})"

        elif action == "move":
            pyautogui.moveTo(x, y, duration=0.2)
            return f"✅ 鼠标移动到 ({x}, {y})"

        elif action == "scroll":
            pyautogui.scroll(clicks, x=x, y=y)
            direction = "上" if clicks > 0 else "下"
            return f"✅ 在 ({x}, {y}) 滚动{direction} {abs(clicks)} 格"

        elif action == "type":
            if not text:
                return "❌ type 操作需要提供 text 参数"
            pyautogui.typewrite(text, interval=0.03)
            return f"✅ 输入文字：{text[:50]}{'...' if len(text) > 50 else ''}"

        elif action == "hotkey":
            if not keys:
                return "❌ hotkey 操作需要提供 keys 参数（如 'ctrl,c'）"
            key_list = [k.strip() for k in keys.split(",")]
            pyautogui.hotkey(*key_list)
            return f"✅ 快捷键：{'+'.join(key_list)}"

        elif action == "press":
            if not key:
                return "❌ press 操作需要提供 key 参数"
            pyautogui.press(key)
            return f"✅ 按键：{key}"

        elif action == "windows":
            import pygetwindow as gw
            wins = gw.getAllTitles()
            visible = [w for w in wins if w.strip()]
            return "当前窗口列表：\n" + "\n".join(f"  • {w}" for w in visible)

        elif action == "focus_window":
            import pygetwindow as gw
            matches = [w for w in gw.getAllWindows()
                       if title.lower() in w.title.lower()]
            if not matches:
                return f"❌ 未找到标题含 '{title}' 的窗口"
            matches[0].activate()
            return f"✅ 已激活窗口：{matches[0].title}"

        return f"❌ 未知 action: {action}"


# ═══════════════════════════════════════════════════════════════════
# KyloBrain 工具：三层记忆 + 元认知 + IDE动手能力
# ═══════════════════════════════════════════════════════════════════

class KyloBrainTool(Tool):
    """KyloBrain 云端大脑 — 记忆查询、经验积累、任务评分、觉醒协议。

    三层记忆：HOT(MEMORY.md) / WARM(本地JSONL) / COLD(GitHub Gist)
    元认知：置信校准、失败模式检测、技能依赖图
    """

    def __init__(self):
        self._connector = None
        self._init_error = None

    def _ensure_connector(self):
        if self._connector is not None:
            return self._connector
        try:
            import sys
            skill_dir = str(Path(__file__).resolve().parent.parent / "skills" / "kylobrain")
            if skill_dir not in sys.path:
                sys.path.insert(0, skill_dir)
            from kylobrain_connector import KyloConnector
            self._connector = KyloConnector()
        except Exception as e:
            self._init_error = str(e)
        return self._connector

    @property
    def name(self) -> str:
        return "kylobrain"

    @property
    def description(self) -> str:
        return (
            "Kylopro 云端大脑：三层记忆管理(HOT/WARM/COLD)、任务前直觉查询(pre_task)、"
            "任务后评分(post_task)、记忆写入(remember)、语义检索(recall)、"
            "记忆巩固(consolidate)、周报(weekly)、成就记录(achieve)、"
            "健康检查(health_check)、觉醒恢复(recover)、迁移清单(migrate)、状态(status)。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "pre_task", "post_task", "remember", "recall",
                        "consolidate", "weekly", "status", "achieve",
                        "health_check", "recover", "migrate", "world_update",
                    ],
                    "description": "操作类型",
                },
                "task": {"type": "string", "description": "任务描述（pre_task/post_task）"},
                "content": {"type": "string", "description": "记忆内容（remember）"},
                "category": {"type": "string", "description": "记忆分类（remember，默认 general）"},
                "query": {"type": "string", "description": "搜索关键词（recall）"},
                "collection": {
                    "type": "string",
                    "enum": ["episodes", "patterns", "failures", "demoted", "consolidated"],
                    "description": "检索的 WARM 层 collection（recall）",
                },
                "outcome": {"type": "string", "description": "任务结果描述（post_task）"},
                "success": {"type": "boolean", "description": "任务是否成功（post_task）"},
                "steps": {"type": "integer", "description": "任务步骤数（post_task）"},
                "duration_sec": {"type": "number", "description": "耗时秒数（post_task）"},
                "title": {"type": "string", "description": "成就标题（achieve）"},
                "description_text": {"type": "string", "description": "成就描述（achieve）"},
                "impact": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "成就影响级别（achieve）",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        conn = self._ensure_connector()
        if not conn:
            return f"⚠️ KyloBrain 初始化失败: {self._init_error}"

        action = kwargs.get("action", "status")

        if action == "pre_task":
            task = kwargs.get("task", "")
            hints = conn.on_task_start(f"tool_{int(datetime.now().timestamp())}", task)
            text = hints.get("prompt_hint_text", "")
            return f"🧠 大脑直觉:\n{text}" if text else "🧠 暂无历史经验，放心执行。"

        elif action == "post_task":
            result = conn.brain.post_task_score(
                task=kwargs.get("task", ""),
                outcome=kwargs.get("outcome", ""),
                steps_taken=kwargs.get("steps", 1),
                duration_sec=kwargs.get("duration_sec", 0),
                success=kwargs.get("success", True),
                errors=[],
            ) if conn.brain else {}
            score = result.get("score", "?")
            return f"📊 任务评分: {score}/100\n{json.dumps(result, ensure_ascii=False, indent=2)}"

        elif action == "remember":
            if conn.brain:
                r = conn.brain.hot.add_entry(
                    kwargs.get("content", ""), kwargs.get("category", "general")
                )
                return f"✅ 已写入 HOT 记忆 ({r['size_bytes']}/{r['limit_bytes']} bytes)"
            return "⚠️ brain 模块未加载"

        elif action == "recall":
            if conn.brain:
                results = conn.brain.warm.search(
                    kwargs.get("query", ""),
                    kwargs.get("collection", "episodes"),
                )
                if not results:
                    return "🔍 未找到相关记忆"
                lines = [f"🔍 找到 {len(results)} 条相关记忆:"]
                for r in results[:5]:
                    lines.append(f"  • {r.get('task', r.get('content', str(r)[:80]))}")
                return "\n".join(lines)
            return "⚠️ brain 模块未加载"

        elif action == "consolidate":
            if conn.brain:
                r = conn.brain.consolidate()
                return f"🧹 记忆巩固完成\n摘要: {r.get('summary', '无')}\n云端同步: {r.get('cold_synced')}"
            return "⚠️ brain 模块未加载"

        elif action == "weekly":
            if conn.brain:
                d = conn.brain.weekly_digest()
                s = d.get("stats", {})
                return (
                    f"📊 {d['week']} 周报\n"
                    f"任务: {s.get('total',0)} 总/{s.get('success',0)} 成功/{s.get('failed',0)} 失败\n"
                    f"成功率: {s.get('rate',0):.0%}"
                )
            return "⚠️ brain 模块未加载"

        elif action == "status":
            status = conn.full_status()
            return json.dumps(status, ensure_ascii=False, indent=2)

        elif action == "achieve":
            conn.on_achievement(
                kwargs.get("title", ""),
                kwargs.get("description_text", ""),
                kwargs.get("impact", "medium"),
            )
            return f"🏆 成就已记录: {kwargs.get('title', '')}"

        elif action == "health_check":
            h = conn.health_check()
            lines = ["🏥 三层记忆健康检查:"]
            for k, v in h.items():
                icon = "✅" if v else "❌"
                lines.append(f"  {icon} {k}")
            return "\n".join(lines)

        elif action == "recover":
            r = conn.emergency_recover()
            return f"🔄 觉醒恢复:\n动作: {r.get('actions', [])}\n恢复后: {r.get('health_after', {})}"

        elif action == "migrate":
            m = conn.migration_checklist()
            lines = ["🚀 迁移检查清单:"]
            for s in m.get("steps", []):
                lines.append(f"  Phase {s['phase']} [{s['status']}] {s['name']}")
            return "\n".join(lines)

        elif action == "world_update":
            return "world_update 需要通过 IDE 桥接执行"

        return f"❌ 未知 action: {action}"


# ═══════════════════════════════════════════════════════════════════
# 编码自适应 read_file — 覆盖 nanobot 默认版本
# 修复：中文 Windows txt 文件（GBK/GB2312/UTF-16）用 UTF-8 读取报错后
# 模型误报"文件为空"的问题
# ═══════════════════════════════════════════════════════════════════

_READ_ENCODINGS = ["utf-8-sig", "utf-8", "gbk", "gb2312", "gb18030", "latin-1"]


# ═══════════════════════════════════════════════════════════════════
# OAuth2 凭证保险箱工具
# 管理平台 OAuth2 token，SQLite + Fernet 加密存储
# ═══════════════════════════════════════════════════════════════════

class OAuth2VaultTool(Tool):
    """OAuth2 凭证保险箱：存储/刷新平台 token，绝不在回复中暴露明文。"""

    @property
    def name(self) -> str:
        return "oauth2_vault"

    @property
    def description(self) -> str:
        return (
            "管理外部平台 OAuth2 凭证。"
            "actions: setup（配置凭证）/ status（查看已配置平台）/ get_token（获取有效token）/ delete（删除平台凭证）。"
            "凭证加密存储，token 永远不出现在回复中。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["setup", "status", "get_token", "delete"],
                    "description": "操作类型",
                },
                "platform": {
                    "type": "string",
                    "description": "平台名（如 feishu, notion）",
                },
                "app_id": {"type": "string", "description": "飞书/平台 App ID"},
                "app_secret": {"type": "string", "description": "飞书/平台 App Secret"},
                "user_open_id": {"type": "string", "description": "飞书用户 open_id（用于发 DM 通知）"},
                "folder_token": {"type": "string", "description": "飞书文件夹 token（默认存放文档的位置）"},
                "chat_id": {"type": "string", "description": "飞书群组 chat_id（向群发送通知）"},
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]
        try:
            from skills.oauth2_vault.vault import get_oauth2_vault
            vault = get_oauth2_vault()
        except Exception as e:
            return f"❌ OAuth2Vault 初始化失败: {e}"

        if action == "setup":
            platform = kwargs.get("platform", "feishu")
            app_id = kwargs.get("app_id", "")
            app_secret = kwargs.get("app_secret", "")
            if not app_id or not app_secret:
                return "❌ setup 需要提供 app_id 和 app_secret"
            creds: dict = {
                "app_id": app_id,
                "app_secret": app_secret,
                "expires_at": 0,  # 初始标记为立即过期，下次使用时自动刷新
            }
            if kwargs.get("user_open_id"):
                creds["user_open_id"] = kwargs["user_open_id"]
            if kwargs.get("folder_token"):
                creds["folder_token"] = kwargs["folder_token"]
            if kwargs.get("chat_id"):
                creds["chat_id"] = kwargs["chat_id"]
            vault.store(platform, creds)
            # 注册 refresher（飞书）
            if platform == "feishu":
                try:
                    from skills.oauth2_vault.platforms.feishu import ensure_feishu_registered
                    ensure_feishu_registered()
                except Exception:
                    pass
            return (
                f"✅ {platform} 凭证已加密存储\n"
                f"app_id: {app_id[:8]}***\n"
                f"下次调用时将自动获取 app_access_token"
            )

        elif action == "status":
            platforms = vault.list_platforms()
            if not platforms:
                return "📭 暂无已配置的平台\n使用 oauth2_vault(action='setup', platform='feishu', ...) 配置"
            lines = ["🔐 OAuth2 已配置平台:"]
            for p in platforms:
                exp = "⚠️ 已过期" if p["expired"] else "✅ 有效"
                import time as _time
                from datetime import datetime
                updated = datetime.fromtimestamp(p["updated_at"]).strftime("%m-%d %H:%M")
                lines.append(f"  · {p['platform']}  {exp}  (更新: {updated})")
            return "\n".join(lines)

        elif action == "get_token":
            platform = kwargs.get("platform", "feishu")
            if not vault.has_platform(platform):
                return f"❌ {platform} 未配置，请先 setup"
            # 触发自动刷新
            if platform == "feishu":
                try:
                    from skills.oauth2_vault.platforms.feishu import ensure_feishu_registered
                    ensure_feishu_registered()
                except Exception:
                    pass
            try:
                from skills.oauth2_vault.auth_middleware import get_middleware
                token = get_middleware().get_valid_token(platform)
                if not token:
                    return f"❌ {platform} token 获取失败（可能需要重新配置 app_secret）"
                return vault.safe_summary(platform)
            except Exception as e:
                return f"❌ token 获取异常: {e}"

        elif action == "delete":
            platform = kwargs.get("platform", "")
            if not platform:
                return "❌ 需要指定 platform"
            ok = vault.delete(platform)
            return f"{'✅ 已删除' if ok else '⚠️ 未找到'} {platform} 凭证"

        return f"❌ 未知 action: {action}"


# ═══════════════════════════════════════════════════════════════════
# 飞书文档 + 消息操作工具
# 创建文档、追加内容、发送消息通知
# ═══════════════════════════════════════════════════════════════════

class FeishuTool(Tool):
    """飞书操作工具：创建文档、写内容、发送消息。需先配置 oauth2_vault(action='setup', platform='feishu')。"""

    @property
    def name(self) -> str:
        return "feishu"

    @property
    def description(self) -> str:
        return (
            "飞书云文档 + 消息操作。"
            "actions: create_doc（创建并写入文档）/ send_message（发文本消息）/ status（检查token状态）。"
            "使用前需先通过 oauth2_vault 配置飞书凭证。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_doc", "send_message", "status"],
                    "description": "操作类型",
                },
                "title": {
                    "type": "string",
                    "description": "文档标题（create_doc 时必填）",
                },
                "content": {
                    "type": "string",
                    "description": "文档 Markdown 内容（支持 # ## ### 标题，段落，--- 分割线，- 列表项）",
                },
                "notify": {
                    "type": "boolean",
                    "description": "创建文档后是否发飞书消息通知用户（需已配置 user_open_id 或 chat_id）",
                },
                "text": {
                    "type": "string",
                    "description": "要发送的消息文本（send_message 时必填）",
                },
                "receive_id": {
                    "type": "string",
                    "description": "接收人 ID（send_message 时，不填则使用已配置的 user_open_id）",
                },
                "receive_id_type": {
                    "type": "string",
                    "enum": ["open_id", "chat_id", "user_id"],
                    "description": "接收人 ID 类型（默认 open_id）",
                },
            },
            "required": ["action"],
        }

    def _get_middleware_and_creds(self):
        from skills.oauth2_vault.auth_middleware import get_middleware
        from skills.oauth2_vault.vault import get_oauth2_vault
        from skills.oauth2_vault.platforms.feishu import ensure_feishu_registered
        ensure_feishu_registered()
        mw = get_middleware()
        vault = get_oauth2_vault()
        creds = vault.get("feishu") or {}
        return mw, creds

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs["action"]

        try:
            mw, creds = self._get_middleware_and_creds()
        except Exception as e:
            return f"❌ 飞书初始化失败: {e}\n请先执行 oauth2_vault(action='setup', platform='feishu', app_id=..., app_secret=...)"

        if action == "status":
            from skills.oauth2_vault.vault import get_oauth2_vault
            vault = get_oauth2_vault()
            if not vault.has_platform("feishu"):
                return "❌ 飞书未配置。请先 oauth2_vault(action='setup', platform='feishu', app_id=..., app_secret=...)"
            summary = vault.safe_summary("feishu")
            extra = []
            if creds.get("user_open_id"):
                extra.append(f"user_open_id: {creds['user_open_id'][:8]}***")
            if creds.get("folder_token"):
                extra.append(f"folder_token: {creds['folder_token'][:8]}***")
            if creds.get("chat_id"):
                extra.append(f"chat_id: {creds['chat_id'][:8]}***")
            return summary + ("\n" + "\n".join(extra) if extra else "")

        elif action == "create_doc":
            title = kwargs.get("title", "未命名文档")
            content = kwargs.get("content", "")
            notify = kwargs.get("notify", True)

            from skills.oauth2_vault.platforms.feishu import create_and_notify

            def _create(token: str) -> dict:
                notify_open_id = creds.get("user_open_id", "") if notify else ""
                notify_chat_id = creds.get("chat_id", "") if (notify and not notify_open_id) else ""
                folder_token = creds.get("folder_token", "")
                return create_and_notify(
                    token=token,
                    title=title,
                    markdown_content=content,
                    notify_open_id=notify_open_id,
                    notify_chat_id=notify_chat_id,
                    folder_token=folder_token,
                )

            result = mw.execute_with_auth(
                platform="feishu",
                task_name=f"create_doc:{title[:30]}",
                fn=_create,
                tags=["create_doc"],
            )

            if not result["success"]:
                if result.get("need_reauth"):
                    return f"❌ {result['error']}"
                return f"❌ 创建文档失败: {result.get('error', '未知错误')}"

            output = result["output"]
            lines = [
                f"✅ 飞书文档已创建",
                f"📄 标题: {output.get('title', title)}",
                f"🔗 链接: {output.get('document_url', '（获取失败）')}",
            ]
            if output.get("blocks_written"):
                lines.append(f"📝 写入段落数: {output['blocks_written']}")
            if output.get("notified"):
                lines.append("📬 已发送飞书通知")
            elif notify and not output.get("notified"):
                lines.append("⚠️ 通知未发送（请检查 user_open_id/chat_id 配置）")
            return "\n".join(lines)

        elif action == "send_message":
            text = kwargs.get("text", "")
            if not text:
                return "❌ send_message 需要提供 text"
            receive_id = kwargs.get("receive_id") or creds.get("user_open_id", "")
            receive_id_type = kwargs.get("receive_id_type", "open_id")
            if not receive_id:
                return "❌ 未指定 receive_id，且飞书未配置 user_open_id"

            from skills.oauth2_vault.platforms.feishu import FeishuAdapter

            def _send(token: str):
                return FeishuAdapter.send_text_message(
                    token, receive_id, text, receive_id_type
                )

            result = mw.execute_with_auth(
                platform="feishu",
                task_name="send_message",
                fn=_send,
                tags=["send_message"],
            )
            if not result["success"]:
                return f"❌ 发送失败: {result.get('error', '未知')}"
            msg_id = result.get("output", {}).get("message_id", "")
            return f"✅ 飞书消息已发送 (message_id: {msg_id[:12]}...)" if msg_id else "✅ 飞书消息已发送"

        return f"❌ 未知 action: {action}"


class KyloReadFileTool(Tool):
    """encoding-aware read_file — 自动尝试常见编码，避免中文 Windows 文件读为空。"""

    def __init__(self, workspace: Path):
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path. Automatically detects encoding (utf-8, gbk, gb2312, latin-1)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read. Absolute or relative to workspace."
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        try:
            p = Path(path).expanduser()
            if not p.is_absolute():
                p = self._workspace / p
            p = p.resolve()

            if not p.exists():
                return f"Error: File not found: {path}"
            if not p.is_file():
                return f"Error: Not a file: {path}"

            raw = p.read_bytes()
            if not raw:
                return ""

            last_err = None
            for enc in _READ_ENCODINGS:
                try:
                    return raw.decode(enc)
                except (UnicodeDecodeError, LookupError) as e:
                    last_err = e
                    continue

            # latin-1 is a superset of byte values, should never fail — but just in case:
            return f"Error: could not decode {path} with any known encoding. Last error: {last_err}"

        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {e}"


def register_kylopro_tools(agent_loop) -> None:
    """
    将 Kylopro 自定义工具注册到 nanobot AgentLoop。
    
    用法：
        from kylopro_tools import register_kylopro_tools
        agent_loop = AgentLoop(...)
        register_kylopro_tools(agent_loop)
    """
    bridge = TaskBridge(workspace=agent_loop.workspace)
    agent_loop.subagents.task_bridge = bridge
    agent_loop.tools.register(TaskInboxTool(workspace=agent_loop.workspace))
    agent_loop.tools.register(DeepThinkTool(provider=agent_loop.provider))
    agent_loop.tools.register(TaskReadTool(bridge=bridge))
    agent_loop.tools.register(TaskWriteTool(bridge=bridge))
    agent_loop.tools.register(TaskInterruptTool(bridge=bridge))

    # 搜索 + 财务工具
    tracker = get_tracker(workspace=agent_loop.workspace)
    agent_loop.tools.register(TavilySearchTool(tracker=tracker, workspace=agent_loop.workspace))
    agent_loop.tools.register(DuckDuckGoSearchTool(tracker=tracker))
    agent_loop.tools.register(CostCheckTool(tracker=tracker))
    agent_loop.tools.register(SetWeeklyBudgetTool(tracker=tracker))

    # 本地脑：Ollama L0 层（零成本）
    agent_loop.tools.register(LocalThinkTool(workspace=agent_loop.workspace))

    # 屏幕操作：截图 / 鼠标 / 键盘 / 窗口
    agent_loop.tools.register(ScreenTool())

    # KyloBrain：三层记忆 + 元认知 + 觉醒协议
    agent_loop.tools.register(KyloBrainTool())

    # OAuth2 凭证保险箱：飞书 / Notion / 未来平台 token 管理
    agent_loop.tools.register(OAuth2VaultTool())
    agent_loop.tools.register(FeishuTool())

    # 覆盖 nanobot 默认 read_file：加编码自适应（修复中文 GBK/UTF-16 txt 读空问题）
    agent_loop.tools.register(KyloReadFileTool(workspace=agent_loop.workspace))
