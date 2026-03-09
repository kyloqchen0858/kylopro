"""
OllamaProvider — 本地 Ollama 模型 Provider，实现 nanobot 的 LLMProvider 接口。

用途：
  - HeartbeatService._decide() — 用 qwen2.5:7b 做 skip/run 决策，零 API 成本
  - LocalThinkTool mode=chat/reason — 路由层可直接调用
  - Future: SubagentManager spawn(local=True)

架构原则：
  - 实现 nanobot LLMProvider ABC，与框架完全兼容
  - 不修改 nanobot 原有 acompletion 全局状态
  - Ollama 不可用时优雅降级（返回 finish_reason="error"）
"""

from __future__ import annotations

import json
import secrets
import string
from typing import Any

from loguru import logger

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

OLLAMA_BASE = "http://localhost:11434"

_ALNUM = string.ascii_letters + string.digits


def _short_id() -> str:
    return "".join(secrets.choice(_ALNUM) for _ in range(9))


def is_ollama_available() -> bool:
    """TCP 探测——返回 True 表示 Ollama 正在监听 localhost:11434。"""
    import socket
    try:
        socket.create_connection(("localhost", 11434), timeout=1).close()
        return True
    except OSError:
        return False


class OllamaProvider(LLMProvider):
    """
    本地 Ollama Provider，nanobot LLMProvider 接口的本地实现。

    通过 aiohttp 直接调用 http://localhost:11434/api/chat，
    支持 tool_calls（函数调用），可用于 HeartbeatService 的 _decide 阶段。
    """

    def __init__(self, default_model: str = "qwen2.5:7b"):
        super().__init__(api_key=None, api_base=OLLAMA_BASE)
        self.default_model = default_model

    def get_default_model(self) -> str:
        return self.default_model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> LLMResponse:
        """调用本地 Ollama /api/chat，返回 LLMResponse（含 tool_calls 支持）。"""
        import aiohttp

        # 去掉 "ollama/" 前缀，Ollama API 只要裸模型名
        model_name = (model or self.default_model).removeprefix("ollama/")

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": self._sanitize_empty_content(messages),
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{OLLAMA_BASE}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=90),
                ) as resp:
                    if resp.status == 404:
                        body = await resp.text()
                        logger.warning("Ollama model '{}' not found", model_name)
                        return LLMResponse(
                            content=f"⚠️ 本地模型 '{model_name}' 未找到。运行: ollama pull {model_name}",
                            finish_reason="error",
                        )
                    if resp.status != 200:
                        body = await resp.text()
                        return LLMResponse(
                            content=f"Ollama error {resp.status}: {body[:300]}",
                            finish_reason="error",
                        )
                    data = await resp.json()

        except (OSError, ConnectionRefusedError):
            logger.debug("Ollama not running at localhost:11434")
            return LLMResponse(
                content="⚠️ Ollama 服务未运行 (localhost:11434)。启动: ollama serve",
                finish_reason="error",
            )
        except Exception as e:
            return LLMResponse(
                content=f"Ollama 连接错误: {e}",
                finish_reason="error",
            )

        message = data.get("message", {})
        content: str | None = message.get("content") or None
        tool_calls_raw: list[dict] = message.get("tool_calls") or []

        tool_calls: list[ToolCallRequest] = []
        for tc in tool_calls_raw:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(ToolCallRequest(
                id=_short_id(),
                name=fn.get("name", "unknown"),
                arguments=args,
            ))

        done_reason = data.get("done_reason", "stop")
        finish_reason = "tool_calls" if tool_calls else done_reason

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )


def create_local_provider(model: str = "qwen2.5:7b") -> OllamaProvider | None:
    """
    若 Ollama 可用，返回 OllamaProvider；否则返回 None。
    由 tools_init.py 导出，供 commands.py 心跳服务使用。
    """
    if is_ollama_available():
        logger.info("Local Ollama available — using '{}' for heartbeat", model)
        return OllamaProvider(default_model=model)
    logger.debug("Ollama not available — heartbeat will use cloud provider")
    return None
