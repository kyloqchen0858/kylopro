"""
Kylopro 双核路由 Provider
========================
实现 DeepSeek（云端高智商）+ Ollama（本地低耗能）的智能任务路由。

路由规则：
  - task_type="routine" 或关键词匹配 → Ollama（本地）
  - 复杂推理/代码/决策 → DeepSeek（云端）
  - 任意一侧失败 → 静默降级切换，绝不阻断运行

扩展槽：在 .env 中填入对应 API Key 即可激活其他厂商
Gemini-CLI 协作接口预留（spawn_gemini_cli 方法）
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger
from openai import AsyncOpenAI
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from core.config import load_nanobot_config, get_soul_prompt, get_env_var

# 确保 Windows 控制台使用 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except AttributeError:
    pass

# PROVIDER_SLOTS 配置保持不变
PROVIDER_SLOTS: dict[str, dict[str, str]] = {
    # [OK] 当前主力：DeepSeek 云端大脑（高智商/复杂推理）
    "deepseek": {
        "api_key_env":   "DEEPSEEK_API_KEY",
        "api_base":      "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "desc":          "高智商/复杂推理/代码生成",
    },
    # [OK] 当前主力：Ollama 本地大脑（低耗能/隐私优先）
    "ollama": {
        "api_key_env":   "",                 # Ollama 无需 API Key
        "api_base":      "OLLAMA_BASE_URL",  # 读取 env var 作为 URL
        "default_model": "OLLAMA_MODEL",     # 读取 env var 作为模型名
        "desc":          "本地低耗能/文件监控/心跳",
    },
    # [VISION] 多模态大脑：Gemini（处理图片/长文档）
    "gemini": {
        "api_key_env":   "GEMINI_API_KEY",
        "api_base":      "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-1.5-flash",
        "desc":          "多模态/长文档阅读",
    },
}

# Routine 任务关键词（命中则自动路由到本地 Ollama）
_ROUTINE_KEYWORDS = [
    "监控", "心跳", "日志", "文件扫描", "定时", "heartbeat",
    "file scan", "log analysis", "routine", "cron", "summary",
    "摘要", "总结", "扫描", "巡检",
]

# 复杂推理与编程关键词（统一使用 deepseek-reasoner，需要链式思考）
_REASONING_KEYWORDS = [
    "为什么", "分析", "推理", "解释", "对比", "评估", "判断",
    "why", "analyze", "reasoning", "compare", "evaluate", "tradeoff",
    "架构设计", "方案设计", "技术选型", "利弊分析",
    "数学模型", "逐步推导", "step by step", "prove",
    "代码", "函数", "调试", "bug", "编程", "python", "javascript", "typescript",
    "class", "def ", "import ", "algorithm", "算法", "sql", "api",
    "接口", "refactor", "重构", "script", "脚本", "implement", "实现",
    "function", "error", "报错", "异常", "unittest", "测试用例",
]


# 危险操作关键词（触发 Human-in-the-Loop 拦截）
_DANGEROUS_KEYWORDS = [
    "rm -rf", "del /f", "format c:", "drop table", "delete from",
    "transfer", "send eth", "send btc", "password change",
    "永久删除", "清空数据库", "转账", "密码修改",
]


class KyloproProvider(LLMProvider):
    """
    Kylopro 双核路由 Provider。
    """

    def __init__(self) -> None:
        self._deepseek_key   = get_env_var("DEEPSEEK_API_KEY")
        self._ollama_base    = get_env_var("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model   = get_env_var("OLLAMA_MODEL", "deepseek-r1:latest")
        self._deepseek_model = get_env_var("DEEPSEEK_MODEL", "deepseek-chat")
        self._gemini_key     = get_env_var("GEMINI_API_KEY")
        self._gemini_model   = get_env_var("GEMINI_MODEL", "gemini-1.5-flash")

        # DeepSeek 客户端
        self._deepseek_client = AsyncOpenAI(
            api_key=self._deepseek_key,
            base_url="https://api.deepseek.com",
        ) if self._deepseek_key else None

        # Ollama 客户端
        self._ollama_client = AsyncOpenAI(
            api_key="ollama",
            base_url=f"{self._ollama_base}/v1",
        )

        # Gemini 客户端（用于视觉任务）
        self._gemini_client = AsyncOpenAI(
            api_key=self._gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta",
        ) if self._gemini_key else None

        logger.info("KyloproProvider 初始化完成 (Dual-Core + Vision Slot)")
    
    def get_default_model(self) -> str:
        """获取默认模型（实现抽象方法）"""
        return self._deepseek_model or "deepseek-chat"

    def _get_system_prompt(self) -> str:
        """获取灵魂指令。"""
        return get_soul_prompt()

    def _apply_nanobot_config(self) -> None:
        """应用外部配置。"""
        config = load_nanobot_config()
        if not config: return
        
        providers = config.get("providers", {})
        if not self._deepseek_key:
            self._deepseek_key = providers.get("deepseek", {}).get("apiKey", "")
            
        agents_model = config.get("agents", {}).get("defaults", {}).get("model", "")
        if agents_model and not get_env_var("DEEPSEEK_MODEL"):
            self._deepseek_model = agents_model

    # -----------------------------------------------------------
    # 路由判断
    # -----------------------------------------------------------

    def _should_use_local(self, messages: list[dict], task_type: str = "auto") -> bool:
        """
        判断是否使用本地 Ollama（低耗能模式）。

        优先级：
          1. 显式 task_type="routine" → 本地
          2. 消息内容命中关键词 → 本地
          3. DeepSeek 未配置 → 强制本地
          4. 默认 → 云端 DeepSeek
        """
        if task_type == "routine":
            return True
        recent_text = " ".join(
            str(m.get("content", "")) for m in messages[-3:]
        ).lower()
        if any(kw in recent_text for kw in _ROUTINE_KEYWORDS):
            logger.debug("路由判断: 命中 routine 关键词 -> Ollama")
            return True
        if not self._deepseek_key:
            logger.warning("DeepSeek 未配置，强制使用本地 Ollama")
            return True
        return False

    def _select_deepseek_model(self, messages: list[dict], task_type: str = "auto") -> str:
        """
        DeepSeek 模型自动选择器。

        返回规则（优先级递减）：
          1. task_type="reason" 或 "code" → deepseek-reasoner（复杂推理与编程）
          2. task_type="chat"           → deepseek-chat（对话，省 token）
          3. task_type="auto"           → 内容关键词自动判断：
               推理/编程关键词           → deepseek-reasoner
               其他                     → deepseek-chat（默认）
        """
        # 显式指定
        if task_type in ("reason", "code"):
            return "deepseek-reasoner"
        if task_type == "chat":
            return "deepseek-chat"

        # 自动检测（最近 3 条消息）
        recent_text = " ".join(
            str(m.get("content", "")) for m in messages[-3:]
        ).lower()

        if any(kw in recent_text for kw in _REASONING_KEYWORDS):
            logger.info("[MODEL] 关键词匹配 -> deepseek-reasoner")
            return "deepseek-reasoner"

        logger.debug("[MODEL] 默认 -> deepseek-chat")
        return "deepseek-chat"

    def _safety_check(self, messages: list[dict]) -> bool:
        """
        Human-in-the-Loop 安全拦截。
        检测危险操作关键词，要求人工 CLI 确认。
        硬编码在此处，不可被 Kylopro 自身绕过。
        """
        last_content = str(messages[-1].get("content", "")).lower() if messages else ""
        triggered = [kw for kw in _DANGEROUS_KEYWORDS if kw in last_content]
        if triggered:
            logger.warning("[SAFETY] 安全拦截触发！检测到关键词: {}", triggered)
            try:
                answer = input(
                    f"\n[KYLOPRO 安全红线] 检测到高风险操作关键词: {triggered}\n"
                    f"输入 'YES' 确认继续执行（任何其他输入中止）: "
                )
                return answer.strip().upper() == "YES"
            except (EOFError, KeyboardInterrupt):
                return False
        return True

    # -----------------------------------------------------------
    # 核心对话接口
    # -----------------------------------------------------------

    def _has_images(self, messages: list[dict]) -> bool:
        """检查消息中是否包含图片。"""
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
        return False

    def _sanitize_empty_content(self, messages: list[dict]) -> list[dict]:
        """修复空内容。"""
        return [m for m in messages if m.get("content") or m.get("tool_calls")]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse:
        """实现 nanobot LLMProvider 接口。"""
        # 预处理：修复空内容
        messages = self._sanitize_empty_content(messages)

        # 1. 视觉任务优先路由
        if self._has_images(messages):
            if self._gemini_client:
                logger.info("[VISION] 检测到图片，路由 -> Gemini ({})", self._gemini_model)
                resp = await self._gemini_client.chat.completions.create(
                    model=self._gemini_model,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return self._to_llm_response(resp)
            else:
                logger.warning("检测到图片但未配置 GEMINI_API_KEY，降级到 DeepSeek（可能报错）")

        # 2. 安全检查
        if not self._safety_check(messages):
            return LLMResponse(content="[拦截] 操作已被安全拦截，未执行。")

        # 3. 路由判断
        use_local = self._should_use_local(messages)
        
        if use_local:
            resp = await self._chat_ollama_raw(messages, tools, model, max_tokens, temperature)
            return self._to_llm_response(resp)
        else:
            selected_model = model or self._select_deepseek_model(messages)
            try:
                resp = await self._chat_deepseek_raw(
                    messages, tools, selected_model, max_tokens, temperature
                )
                return self._to_llm_response(resp)
            except Exception as e:
                logger.warning("DeepSeek 调用失败（{}），静默降级到 Ollama", e)
                resp = await self._chat_ollama_raw(messages, tools, None, max_tokens, temperature)
                return self._to_llm_response(resp)

    async def _chat_deepseek_raw(self, messages, tools, model, max_tokens, temperature):
        _model = model or self._deepseek_model
        kwargs = {"model": _model, "messages": messages, "max_tokens": max_tokens}
        if _model != "deepseek-reasoner":
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return await self._deepseek_client.chat.completions.create(**kwargs)

    async def _chat_ollama_raw(self, messages, tools, model, max_tokens, temperature):
        _model = model or self._ollama_model
        kwargs = {"model": _model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return await self._ollama_client.chat.completions.create(**kwargs)

    def _to_llm_response(self, resp: Any) -> LLMResponse:
        """转换为 nanobot 标准响应。"""
        choice = resp.choices[0]
        msg = choice.message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments or "{}"),
                ))
        return LLMResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            reasoning_content=getattr(msg, "reasoning_content", None),
        )

    # 保留原有的方法名以兼容其他模块
    async def chat_legacy(self, *args, **kwargs):
        return await self.chat(*args, **kwargs)

    def _is_thinking_mode(self, model: str, enable_thinking: bool) -> bool:
        """判断是否处于思考模式。"""
        return model == "deepseek-reasoner" or enable_thinking

    async def _chat_deepseek(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        model: str | None,
        max_tokens: int,
        temperature: float,
        enable_thinking: bool = False,
    ) -> dict:
        """
        调用 DeepSeek API（openai 兼容接口）。

        思考模式适配：
          - deepseek-reasoner: 自动开启思考模式
          - deepseek-chat + enable_thinking=True: 通过 extra_body 开启
          - 思考模式下 temperature/top_p 等参数不生效，自动跳过
        """
        assert self._deepseek_client, "DeepSeek 客户端未初始化"
        _model = model or self._deepseek_model
        thinking = self._is_thinking_mode(_model, enable_thinking)
        logger.info("[CLOUD] 路由 -> DeepSeek ({}) {}", _model, "[思考模式]" if thinking else "")

        kwargs: dict[str, Any] = {
            "model":       _model,
            "messages":    messages,
            "max_tokens":  max_tokens,
        }

        # 思考模式下 temperature 不生效，跳过避免混淆
        if not thinking:
            kwargs["temperature"] = temperature

        # deepseek-chat 需要通过 extra_body 显式开启思考模式
        # deepseek-reasoner 自动开启，无需额外参数
        if enable_thinking and _model != "deepseek-reasoner":
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = await self._deepseek_client.chat.completions.create(**kwargs)

        if hasattr(resp, "usage") and resp.usage:
            prompt_tk = resp.usage.prompt_tokens
            comp_tk = getattr(resp.usage, "completion_tokens", 0)
            cache_tk = getattr(resp.usage, "prompt_cache_hit_tokens", 0)
            logger.info("[TOKEN] DeepSeek {} 消耗 | Prompt: {} (Cache Hit: {}) | Completion: {}",
                        _model, prompt_tk, cache_tk, comp_tk)

        return self._normalize_response(resp)

    async def _chat_ollama(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        model: str | None,
        max_tokens: int,
        temperature: float,
    ) -> dict:
        """调用本地 Ollama（openai 兼容接口）。"""
        _model = model or self._ollama_model
        logger.info("[LOCAL] 路由 -> Ollama ({})", _model)

        kwargs: dict[str, Any] = {
            "model":       _model,
            "messages":    messages,
            "max_tokens":  max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            resp = await self._ollama_client.chat.completions.create(**kwargs)
            return self._normalize_response(resp)
        except Exception as e:
            logger.error("Ollama 调用失败 (是否已运行 ollama serve?): {}", e)
            return {
                "content": f"[Ollama 不可用] 请确认已运行 `ollama serve`。错误: {e}",
                "tool_calls": [],
            }

    @staticmethod
    def _normalize_response(resp: Any) -> dict[str, Any]:
        """将 openai SDK 响应标准化为统一字典格式（含 reasoning_content）。"""
        choice = resp.choices[0]
        msg = choice.message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id":        tc.id,
                    "name":      tc.function.name,
                    "arguments": json.loads(tc.function.arguments or "{}"),
                })
        return {
            "content":            msg.content or "",
            "reasoning_content":  getattr(msg, "reasoning_content", None) or "",
            "tool_calls":         tool_calls,
            "finish_reason":      choice.finish_reason,
            "_raw_message":       msg,  # 保留原始消息对象，用于工具调用循环
        }

    # -----------------------------------------------------------
    # 思考模式工具调用循环
    # -----------------------------------------------------------

    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Any = None,
        model: str | None = None,
        max_tokens: int = 16384,
        task_type: str = "auto",
        enable_thinking: bool = False,
        max_sub_turns: int = 10,
    ) -> dict[str, Any]:
        """
        思考模式下的多轮工具调用循环。

        DeepSeek 思考模式允许模型在回答问题过程中进行多轮思考+工具调用，
        在此过程中必须将 reasoning_content 回传给 API。

        Args:
            messages:       对话消息列表（会被原地修改）
            tools:          工具定义列表
            tool_executor:  工具执行器，callable(name, arguments) -> str
                            如果为 None，则只执行一轮（不自动调用工具）
            model:          模型名，None 时自动路由
            max_tokens:     最大 token 数
            task_type:      任务类型
            enable_thinking: 是否开启思考模式
            max_sub_turns:  最大子轮次（防止无限循环）

        Returns:
            最终的 normalized response dict
        """
        selected_model = model or self._select_deepseek_model(messages, task_type)
        thinking = self._is_thinking_mode(selected_model, enable_thinking)

        sub_turn = 0
        while sub_turn < max_sub_turns:
            sub_turn += 1

            result = await self._chat_deepseek(
                messages=messages,
                tools=tools,
                model=selected_model,
                max_tokens=max_tokens,
                temperature=0.1,
                enable_thinking=enable_thinking,
            )

            raw_msg = result.get("_raw_message")
            reasoning = result.get("reasoning_content", "")
            content = result.get("content", "")
            tool_calls = result.get("tool_calls", [])

            # 将模型的完整响应（含 reasoning_content）追加到消息列表
            if raw_msg is not None:
                # 直接 append 原始消息对象，保留 reasoning_content、content、tool_calls
                messages.append(raw_msg)
            else:
                # fallback: 手动构造
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": content,
                }
                if reasoning and thinking:
                    assistant_msg["reasoning_content"] = reasoning
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id":       tc["id"],
                            "type":     "function",
                            "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                        }
                        for tc in tool_calls
                    ]
                messages.append(assistant_msg)

            if reasoning:
                logger.debug("[THINKING] Sub-turn {}: reasoning={}...",
                             sub_turn, reasoning[:100])

            # 没有工具调用 → 模型已给出最终答案
            if not tool_calls:
                logger.info("[TOOLS] 工具调用循环结束，共 {} 轮", sub_turn)
                return result

            # 没有执行器 → 返回工具调用让上层处理
            if tool_executor is None:
                return result

            # 执行工具调用，将结果追加到消息列表
            for tc in tool_calls:
                logger.info("[TOOLS] 调用工具: {}({})", tc["name"], tc["arguments"])
                try:
                    tool_result = tool_executor(tc["name"], tc["arguments"])
                    if asyncio.iscoroutine(tool_result):
                        tool_result = await tool_result
                    tool_result = str(tool_result)
                except Exception as e:
                    tool_result = f"工具执行错误: {e}"
                    logger.error("[TOOLS] {} 执行失败: {}", tc["name"], e)

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc["id"],
                    "content":      tool_result,
                })

        logger.warning("[TOOLS] 工具调用循环达到上限 {} 轮", max_sub_turns)
        return result  # type: ignore[possibly-undefined]

    @staticmethod
    def clear_reasoning_content(messages: list[dict[str, Any]]) -> None:
        """
        清除消息历史中的 reasoning_content（用于新用户问题开始时）。

        DeepSeek 官方建议：在新 turn 开始时删除之前 turn 的 reasoning_content，
        以节省网络带宽。如果保留了 reasoning_content 发送给 API，API 将会忽略它们。
        """
        for msg in messages:
            # dict 类型的消息
            if isinstance(msg, dict):
                msg.pop("reasoning_content", None)
            # openai SDK 的消息对象
            elif hasattr(msg, "reasoning_content"):
                msg.reasoning_content = None  # type: ignore[attr-defined]

    # -----------------------------------------------------------
    # 连通性测试
    # -----------------------------------------------------------

    async def test_connection(self) -> str:
        """
        验证 DeepSeek 和 Ollama 连通性。
        DeepSeek 使用最简对话（deepseek-chat，非 reasoner），尽量少消耗额度。
        """
        results = []

        # 测试 DeepSeek
        if self._deepseek_client:
            try:
                r = await self._chat_deepseek(
                    messages=[{"role": "user", "content": "reply 'ok' only"}],
                    tools=None,
                    model="deepseek-chat",   # 用 chat 省 token，不用 reasoner
                    max_tokens=5,
                    temperature=0,
                )
                results.append("[OK] DeepSeek: " + r["content"].strip()[:20])
            except Exception as e:
                results.append(f"[FAIL] DeepSeek: {e}")
        else:
            results.append("[SKIP] DeepSeek: 未配置 API Key")

        # 测试 Ollama
        try:
            r = await self._chat_ollama(
                messages=[{"role": "user", "content": "reply 'ok' only"}],
                tools=None,
                model=None,
                max_tokens=5,
                temperature=0,
            )
            content = r["content"].strip()[:30]
            if "[Ollama 不可用]" in content:
                results.append("[FAIL] Ollama: 连接失败，请运行 ollama serve")
            else:
                results.append("[OK] Ollama: " + content)
        except Exception as e:
            results.append(f"[FAIL] Ollama: {e}")

        return "\n".join(results)

    # -----------------------------------------------------------
    # Gemini-CLI 协作预留接口（Phase 3 激活）
    # -----------------------------------------------------------

    async def spawn_gemini_cli(self, prompt: str, timeout: int = 60) -> str:
        """
        Gemini-CLI 协作接口（预留，Phase 3 激活）。

        未来实现：通过 asyncio.subprocess 调用本机安装的 gemini-cli，
        支持 Kylopro 与 Gemini CLI 的 multi-agent 协作。

        用法示例（Phase 3 后）：
            result = await provider.spawn_gemini_cli("分析这段代码...")
        """
        raise NotImplementedError(
            "Gemini-CLI 协作模块待 Phase 3 激活。\n"
            "实现计划：asyncio.create_subprocess_exec('gemini', '-p', prompt)"
        )
