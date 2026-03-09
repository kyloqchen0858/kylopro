"""Direct OpenAI-compatible provider — bypasses LiteLLM."""

from __future__ import annotations

from typing import Any

import json_repair
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from rich import print as rich_print

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class CustomProvider(LLMProvider):

    def __init__(
        self,
        api_key: str = "no-key",
        api_base: str = "http://localhost:8000/v1",
        default_model: str = "default",
        primary_api_base: str | None = None,
        primary_bearer_token: str | None = None,
        primary_extra_headers: dict[str, str] | None = None,
        backup_api_base: str | None = None,
        backup_api_key: str | None = None,
        backup_extra_headers: dict[str, str] | None = None,
        request_timeout: float = 60.0,
    ):
        effective_backup_key = backup_api_key or api_key
        effective_backup_base = backup_api_base or api_base
        super().__init__(effective_backup_key, effective_backup_base)
        self.default_model = default_model
        self._request_timeout = request_timeout

        # 在这里填入逆向代理的 URL 和 Token（仅限你有权使用的授权端点）
        self.primary_api_base = primary_api_base
        self.primary_bearer_token = primary_bearer_token or ""
        self.primary_extra_headers = primary_extra_headers or {}

        # 在这里填入正规备用的 URL 和 API Key
        self.backup_api_base = effective_backup_base
        self.backup_api_key = effective_backup_key
        self.backup_extra_headers = backup_extra_headers or {}

        self._primary_client = self._build_client(
            api_key=self.primary_bearer_token or "no-key",
            api_base=self.primary_api_base,
            extra_headers=self.primary_extra_headers,
        )
        self._backup_client = self._build_client(
            api_key=self.backup_api_key or "no-key",
            api_base=self.backup_api_base,
            extra_headers=self.backup_extra_headers,
        )

    def _build_client(
        self,
        api_key: str,
        api_base: str | None,
        extra_headers: dict[str, str] | None,
    ) -> AsyncOpenAI | None:
        if not api_base:
            return None

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "base_url": api_base,
            "timeout": self._request_timeout,
        }
        if extra_headers:
            client_kwargs["default_headers"] = extra_headers
        return AsyncOpenAI(**client_kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": self._sanitize_empty_content(messages),
            "max_tokens": max(1, max_tokens),
            "temperature": temperature,
        }
        if tools:
            kwargs.update(tools=tools, tool_choice="auto")

        try:
            if self._primary_client is not None:
                try:
                    return self._parse(await self._primary_client.chat.completions.create(**kwargs))
                except Exception as primary_error:
                    self._warn_primary_failure(primary_error)

            if self._backup_client is None:
                raise RuntimeError("No backup API base configured for custom provider.")

            return self._parse(await self._backup_client.chat.completions.create(**kwargs))
        except Exception as e:
            return LLMResponse(content=f"Error: {e}", finish_reason="error")

    def _warn_primary_failure(self, error: Exception) -> None:
        detail = self._format_primary_failure(error)
        rich_print(f"[yellow]Warning: 主路请求失败（{detail}），自动切换至备用正规 API[/yellow]")

    @staticmethod
    def _format_primary_failure(error: Exception) -> str:
        if isinstance(error, APIStatusError):
            return f"HTTP {error.status_code}"
        if isinstance(error, APITimeoutError):
            return "timeout"
        if isinstance(error, APIConnectionError):
            return "connection error"
        return error.__class__.__name__

    def _parse(self, response: Any) -> LLMResponse:
        choice = response.choices[0]
        msg = choice.message
        tool_calls = [
            ToolCallRequest(id=tc.id, name=tc.function.name,
                            arguments=json_repair.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments)
            for tc in (msg.tool_calls or [])
        ]
        u = response.usage
        return LLMResponse(
            content=msg.content, tool_calls=tool_calls, finish_reason=choice.finish_reason or "stop",
            usage={"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens, "total_tokens": u.total_tokens} if u else {},
            reasoning_content=getattr(msg, "reasoning_content", None) or None,
        )

    def get_default_model(self) -> str:
        return self.default_model

