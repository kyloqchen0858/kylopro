"""
Kylopro 双核路由 Provider（增强版）
=====================================
实现智能任务路由，根据任务类型选择最合适的 AI 模型：
  - GLM-4V（视觉任务，含图片时自动路由）
  - Ollama 本地（routine 任务，省钱省延迟）
  - DeepSeek（主力模型，复杂推理/代码）
  - OpenRouter（DeepSeek 不可用时降级）
  - Ollama 兜底（所有云端都失败时）

扩展槽：在 .env 中填入对应 API Key 即可激活其他厂商
"""

from __future__ import annotations

import asyncio
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

# 确保 Windows 控制台使用 UTF-8 输出（兼容 Windows/Linux）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except AttributeError:
    pass

# ---------------------------------------------------------------
# PROVIDER_SLOTS：各 AI 提供商的配置说明（纯文档用途，不被代码读取）
# 实际值由 __init__ 方法中的 get_env_var() 调用从环境变量读取。
# 这里显示的是各字段的默认值（当对应环境变量未设置时使用）。
# ---------------------------------------------------------------
PROVIDER_SLOTS: dict[str, dict[str, str]] = {
    # [OK] 当前主力：DeepSeek 云端大脑（高智商/复杂推理）
    "deepseek": {
        "api_key_env":   "DEEPSEEK_API_KEY",
        "api_base":      "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "desc":          "高智商/复杂推理/代码生成",
    },
    # [OK] 视觉任务：GLM-4V（处理图片/截图）
    "glm": {
        "api_key_env":   "GLM_API_KEY",
        "api_base":      "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4v-flash",
        "desc":          "视觉任务/图片识别/截图分析",
    },
    # [OK] 当前主力：Ollama 本地大脑（低耗能/隐私优先）
    # 注意：api_base 和 default_model 从环境变量读取（修复之前把变量名当成值的 bug）
    "ollama": {
        "api_key_env":   "",
        "api_base":      "http://localhost:11434",   # OLLAMA_BASE_URL 的默认值
        "default_model": "deepseek-r1:latest",       # OLLAMA_MODEL 的默认值
        "desc":          "本地低耗能/routine 任务/隐私保护",
    },
    # [FALLBACK] 降级网关：OpenRouter（DeepSeek 不可用时自动切换）
    "openrouter": {
        "api_key_env":   "OPENROUTER_API_KEY",
        "api_base":      "https://openrouter.ai/api/v1",
        "default_model": "deepseek/deepseek-chat",
        "desc":          "降级网关/多模型路由",
    },
    # [VISION] 多模态大脑：Gemini（处理图片/长文档）
    "gemini": {
        "api_key_env":   "GEMINI_API_KEY",
        "api_base":      "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-1.5-flash",
        "desc":          "多模态/长文档阅读（备用视觉方案）",
    },
}

# Routine 任务关键词（命中则自动路由到本地 Ollama，省钱省延迟）
_ROUTINE_KEYWORDS = [
    "监控", "心跳", "日志", "文件扫描", "定时", "heartbeat",
    "file scan", "log analysis", "routine", "cron", "summary",
    "摘要", "总结", "扫描", "巡检",
]

# 复杂推理与编程关键词（使用 deepseek-reasoner，需要链式思考）
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
    Kylopro 智能路由 Provider。

    路由优先级：
      1. 含图片 → GLM-4V（视觉模型）
      2. 安全检查（危险操作拦截）
      3. routine 任务 → Ollama 本地（省钱）
      4. 复杂推理 → deepseek-reasoner
      5. 普通对话 → deepseek-chat
      6. DeepSeek 失败 → OpenRouter（降级）
      7. 一切失败 → Ollama 本地兜底
    """

    def __init__(self) -> None:
        # ===== DeepSeek 配置 =====
        self._deepseek_key   = get_env_var("DEEPSEEK_API_KEY")
        self._deepseek_model = get_env_var("DEEPSEEK_MODEL", "deepseek-chat")

        # ===== GLM-4V 视觉配置 =====
        self._glm_key   = get_env_var("GLM_API_KEY")
        self._glm_model = get_env_var("GLM_MODEL", "glm-4v-flash")

        # ===== OpenRouter 降级配置 =====
        self._openrouter_key   = get_env_var("OPENROUTER_API_KEY")
        self._openrouter_model = get_env_var("OPENROUTER_MODEL", "deepseek/deepseek-chat")

        # ===== Ollama 本地模型配置 =====
        # 修复：之前 PROVIDER_SLOTS 把变量名字符串当成了值，这里正确使用 get_env_var() 读取
        self._ollama_base         = get_env_var("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model        = get_env_var("OLLAMA_MODEL", "deepseek-r1:latest")
        self._ollama_cloud_model  = get_env_var("OLLAMA_CLOUD_MODEL", "llama3.3:latest")

        # ===== Gemini 视觉配置（备用）=====
        self._gemini_key   = get_env_var("GEMINI_API_KEY")
        self._gemini_model = get_env_var("GEMINI_MODEL", "gemini-1.5-flash")

        # ===== 初始化各 AI 客户端 =====

        # DeepSeek 客户端（主力）
        self._deepseek_client = AsyncOpenAI(
            api_key=self._deepseek_key,
            base_url="https://api.deepseek.com",
        ) if self._deepseek_key else None

        # GLM-4V 客户端（视觉任务）
        self._glm_client = AsyncOpenAI(
            api_key=self._glm_key,
            base_url="https://open.bigmodel.cn/api/paas/v4",
        ) if self._glm_key else None

        # OpenRouter 客户端（降级）
        self._openrouter_client = AsyncOpenAI(
            api_key=self._openrouter_key,
            base_url="https://openrouter.ai/api/v1",
        ) if self._openrouter_key else None

        # Ollama 客户端（本地）
        # 注意：Ollama 不需要真实 key，但 OpenAI 兼容接口格式需要一个占位符
        self._ollama_client = AsyncOpenAI(
            api_key="ollama",
            base_url=f"{self._ollama_base}/v1",
        )

        # Gemini 客户端（备用视觉）
        self._gemini_client = AsyncOpenAI(
            api_key=self._gemini_key,
            base_url="https://generativelanguage.googleapis.com/v1beta",
        ) if self._gemini_key else None

        logger.info("KyloproProvider 初始化完成 (DeepSeek + GLM-4V + Ollama + OpenRouter)")

    def get_default_model(self) -> str:
        """获取默认模型（实现 nanobot LLMProvider 抽象方法）"""
        return self._deepseek_model or "deepseek-chat"

    def _get_system_prompt(self) -> str:
        """获取 Kylopro 灵魂指令（SOUL.md）。"""
        return get_soul_prompt()

    def _apply_nanobot_config(self) -> None:
        """应用外部 nanobot 配置（如 config.json 中的 model 设置）。"""
        config = load_nanobot_config()
        if not config:
            return

        providers = config.get("providers", {})
        if not self._deepseek_key:
            self._deepseek_key = providers.get("deepseek", {}).get("apiKey", "")

        agents_model = config.get("agents", {}).get("defaults", {}).get("model", "")
        if agents_model and not get_env_var("DEEPSEEK_MODEL"):
            self._deepseek_model = agents_model

    # -----------------------------------------------------------
    # 路由判断辅助方法
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
          1. task_type="reason" 或 "code" → deepseek-reasoner（复杂推理）
          2. task_type="chat"             → deepseek-chat（省 token）
          3. task_type="auto"            → 关键词自动判断
        """
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
    # 核心对话接口（nanobot LLMProvider 标准接口）
    # -----------------------------------------------------------

    def _has_images(self, messages: list[dict]) -> bool:
        """检查消息中是否包含图片（用于路由到视觉模型）。"""
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return True
        return False

    def _sanitize_empty_content(self, messages: list[dict]) -> list[dict]:
        """过滤空内容的消息（避免 API 报错）。"""
        return [m for m in messages if m.get("content") or m.get("tool_calls")]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> LLMResponse:
        """
        实现 nanobot LLMProvider 接口。

        智能路由逻辑：
        1. 含图片 → GLM-4V（或 Gemini 备用）
        2. 安全检查
        3. routine 任务 → Ollama 本地
        4. 普通/复杂任务 → DeepSeek（含自动模型选择）
        5. DeepSeek 失败 → OpenRouter 降级
        6. 一切失败 → Ollama 本地兜底
        """
        # 预处理：过滤空内容消息
        messages = self._sanitize_empty_content(messages)

        # 1. 视觉任务优先路由：含图片时用 GLM-4V
        if self._has_images(messages):
            if self._glm_client:
                logger.info("[VISION] 检测到图片，路由 -> GLM-4V ({})", self._glm_model)
                resp = await self._glm_client.chat.completions.create(
                    model=self._glm_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return self._to_llm_response(resp)
            elif self._gemini_client:
                # Gemini 作为视觉备用方案
                logger.info("[VISION] GLM-4V 未配置，降级 -> Gemini ({})", self._gemini_model)
                resp = await self._gemini_client.chat.completions.create(
                    model=self._gemini_model,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return self._to_llm_response(resp)
            else:
                logger.warning("检测到图片但未配置 GLM_API_KEY 或 GEMINI_API_KEY，降级到 DeepSeek（可能无法识别图片）")

        # 2. 安全检查（危险操作拦截）
        if not self._safety_check(messages):
            return LLMResponse(content="[拦截] 操作已被安全拦截，未执行。")

        # 3. routine 任务 → Ollama 本地（省钱优先）
        use_local = self._should_use_local(messages)
        if use_local:
            resp = await self._chat_ollama_raw(messages, tools, model, max_tokens, temperature)
            return self._to_llm_response(resp)

        # 4. 云端路由：DeepSeek（含自动模型选择）
        selected_model = model or self._select_deepseek_model(messages)
        try:
            resp = await self._chat_deepseek_raw(
                messages, tools, selected_model, max_tokens, temperature
            )
            return self._to_llm_response(resp)
        except Exception as e:
            logger.warning("DeepSeek 调用失败（{}），尝试 OpenRouter 降级", e)

        # 5. OpenRouter 降级（DeepSeek 失败时）
        if self._openrouter_client:
            try:
                logger.info("[FALLBACK] 路由 -> OpenRouter ({})", self._openrouter_model)
                resp = await self._openrouter_client.chat.completions.create(
                    model=self._openrouter_model,
                    messages=messages,
                    tools=tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return self._to_llm_response(resp)
            except Exception as e:
                logger.warning("OpenRouter 也失败了（{}），最终兜底到 Ollama", e)

        # 6. 最终兜底：本地 Ollama
        logger.info("[FALLBACK] 最终兜底 -> Ollama 本地")
        resp = await self._chat_ollama_raw(messages, tools, None, max_tokens, temperature)
        return self._to_llm_response(resp)

    # -----------------------------------------------------------
    # 各 AI 后端的原始调用方法（供 chat() 和 test_connection() 使用）
    # -----------------------------------------------------------

    async def _chat_deepseek_raw(self, messages, tools, model, max_tokens, temperature):
        """直接调用 DeepSeek API（openai 兼容接口）。"""
        assert self._deepseek_client, "DeepSeek 客户端未初始化（DEEPSEEK_API_KEY 未配置）"
        _model = model or self._deepseek_model
        kwargs: dict[str, Any] = {
            "model": _model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        # deepseek-reasoner 不支持 temperature 参数
        if _model != "deepseek-reasoner":
            kwargs["temperature"] = temperature
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return await self._deepseek_client.chat.completions.create(**kwargs)

    async def _chat_ollama_raw(self, messages, tools, model, max_tokens, temperature):
        """
        直接调用本地 Ollama 接口（OpenAI 兼容接口）。

        这是最便宜的选项：完全本地运行，无 API 费用。
        适合：日常 routine 任务、网络不可用时的兜底。
        """
        _model = model or self._ollama_model
        logger.info("[LOCAL] 路由 -> Ollama ({})", _model)
        kwargs: dict[str, Any] = {
            "model": _model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            return await self._ollama_client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error("Ollama 调用失败 (model={}, 是否已运行 ollama serve?): {}", _model, e)
            raise

    def _to_llm_response(self, resp: Any) -> LLMResponse:
        """将 openai SDK 响应转换为 nanobot 标准 LLMResponse 格式。"""
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

    # -----------------------------------------------------------
    # 兼容旧版本的方法别名
    # -----------------------------------------------------------

    async def _chat_deepseek(self, messages, tools, model, max_tokens, temperature,
                             enable_thinking: bool = False) -> dict:
        """
        调用 DeepSeek API（兼容旧版本调用，返回 dict 格式）。
        新代码请使用 _chat_deepseek_raw()。
        """
        resp = await self._chat_deepseek_raw(messages, tools, model, max_tokens, temperature)
        return self._normalize_response(resp)

    async def _chat_ollama(self, messages, tools, model, max_tokens, temperature) -> dict:
        """
        调用 Ollama（兼容旧版本调用，返回 dict 格式）。
        新代码请使用 _chat_ollama_raw()。
        """
        try:
            resp = await self._chat_ollama_raw(messages, tools, model, max_tokens, temperature)
            return self._normalize_response(resp)
        except Exception as e:
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
            "content":           msg.content or "",
            "reasoning_content": getattr(msg, "reasoning_content", None) or "",
            "tool_calls":        tool_calls,
            "finish_reason":     choice.finish_reason,
            "_raw_message":      msg,  # 保留原始消息对象
        }

    def _is_thinking_mode(self, model: str, enable_thinking: bool) -> bool:
        """判断是否处于思考模式（deepseek-reasoner 自动开启）。"""
        return model == "deepseek-reasoner" or enable_thinking

    # -----------------------------------------------------------
    # 思考模式工具调用循环（高级用法）
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
            messages:        对话消息列表（会被原地修改）
            tools:           工具定义列表
            tool_executor:   工具执行器，callable(name, arguments) -> str
                             如果为 None，则只执行一轮（不自动调用工具）
            model:           模型名，None 时自动路由
            max_tokens:      最大 token 数
            task_type:       任务类型
            enable_thinking: 是否开启思考模式
            max_sub_turns:   最大子轮次（防止无限循环）

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
            content = result.get("content", "")
            tool_calls = result.get("tool_calls", [])

            # 将模型的完整响应（含 reasoning_content）追加到消息列表
            if raw_msg is not None:
                messages.append(raw_msg)
            else:
                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": content,
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ]
                messages.append(assistant_msg)

            # 如果没有工具调用，对话结束
            if not tool_calls:
                return result

            # 如果没有提供 tool_executor，只执行一轮后返回
            if tool_executor is None:
                logger.warning("[TOOLS] 有工具调用但未提供 tool_executor，停止循环")
                return result

            # 执行工具调用
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
        清除消息历史中的 reasoning_content（在新 turn 开始时调用）。

        DeepSeek 官方建议：新 turn 开始时删除之前的 reasoning_content，
        以节省网络带宽。
        """
        for msg in messages:
            if isinstance(msg, dict):
                msg.pop("reasoning_content", None)
            elif hasattr(msg, "reasoning_content"):
                msg.reasoning_content = None  # type: ignore[attr-defined]

    # -----------------------------------------------------------
    # 连通性测试
    # -----------------------------------------------------------

    async def test_connection(self) -> dict:
        """
        测试所有 AI 接口的连通性。

        返回格式：
        {
            "DeepSeek": "ok" | "failed: 错误信息" | "skipped（未配置）",
            "GLM-4V":   "ok" | "failed: 错误信息" | "skipped（未配置）",
            "Ollama":   "ok" | "failed: 错误信息",
            "OpenRouter": "ok" | "failed: 错误信息" | "skipped（未配置）",
        }
        """
        results: dict[str, str] = {}

        # 测试 DeepSeek
        if self._deepseek_client:
            try:
                r = await self._chat_deepseek_raw(
                    messages=[{"role": "user", "content": "reply 'ok' only"}],
                    tools=None,
                    model="deepseek-chat",  # 用 chat 省 token，不用 reasoner
                    max_tokens=5,
                    temperature=0,
                )
                content = r.choices[0].message.content or ""
                results["DeepSeek"] = "ok: " + content.strip()[:20]
            except Exception as e:
                results["DeepSeek"] = f"failed: {e}"
        else:
            results["DeepSeek"] = "skipped（未配置 DEEPSEEK_API_KEY）"

        # 测试 GLM-4V（有 key 就算配置成功，不实际发请求省钱）
        if self._glm_key:
            results["GLM-4V"] = "ok（key 已配置）"
        else:
            results["GLM-4V"] = "skipped（未配置 GLM_API_KEY）"

        # 测试 Ollama（实际发送请求测试连通性）
        try:
            r = await self._chat_ollama_raw(
                messages=[{"role": "user", "content": "reply 'ok' only"}],
                tools=None,
                model=None,
                max_tokens=5,
                temperature=0,
            )
            content = r.choices[0].message.content or ""
            if content.strip():
                results["Ollama"] = "ok: " + content.strip()[:30]
            else:
                results["Ollama"] = "ok（返回空内容，ollama 运行中）"
        except Exception as e:
            results["Ollama"] = f"failed: {e}（请确认已运行 ollama serve）"

        # 测试 OpenRouter（如果配置了）
        if self._openrouter_client:
            try:
                r = await self._openrouter_client.chat.completions.create(
                    model=self._openrouter_model,
                    messages=[{"role": "user", "content": "reply 'ok' only"}],
                    max_tokens=5,
                )
                content = r.choices[0].message.content or ""
                results["OpenRouter"] = "ok: " + content.strip()[:20]
            except Exception as e:
                results["OpenRouter"] = f"failed: {e}"
        else:
            results["OpenRouter"] = "skipped（未配置 OPENROUTER_API_KEY）"

        # 打印格式化结果
        for service, status in results.items():
            if status.startswith("ok"):
                icon = "✅"
            elif "skipped" in status:
                icon = "⚠️"
            else:
                icon = "❌"
            print(f"  {icon} {service}: {status}")

        return results

    # -----------------------------------------------------------
    # Gemini-CLI 协作预留接口（Phase 3 激活）
    # -----------------------------------------------------------

    async def spawn_gemini_cli(self, prompt: str, timeout: int = 60) -> str:
        """
        Gemini-CLI 协作接口（预留，Phase 3 激活）。

        未来实现：通过 asyncio.subprocess 调用本机安装的 gemini-cli，
        支持 Kylopro 与 Gemini CLI 的 multi-agent 协作。
        """
        raise NotImplementedError(
            "Gemini-CLI 协作模块待 Phase 3 激活。\n"
            "实现计划：asyncio.create_subprocess_exec('gemini', '-p', prompt)"
        )
