"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import AsyncExitStack
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import WebFetchTool, WebSearchTool
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import ChannelsConfig, ExecToolConfig
    from nanobot.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """

    _TOOL_RESULT_MAX_CHARS = 500
    _TERMINAL_TOOL_RESULT_MAX_CHARS = 1500
    _TERMINAL_MARKERS = ("[DONE]", "[FAILED]")
    _EXTERNAL_API_TOOLS = {"feishu", "oauth2_vault", "freelance"}
    _MERGE_WINDOW_SEC = 1.2
    _AMBIGUOUS_SHORT_LEN = 10
    _AMBIGUOUS_PATTERNS = (
        r"^(继续|接着|然后|安排一下|处理一下|搞一下|看下|看看|优化一下|改一下|修一下|推进一下)[。!！\s]*$",
        r"^(ok|好的|行|继续上班)[。!！\s]*$",
    )
    _CONCRETE_HINT_WORDS = (
        "飞书", "notion", "文档", "消息", "代码", "文件", "日志", "测试", "部署",
        "配置", "修复", "重启", "search", "grep", "read_file", "exec",
    )

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        brave_api_key: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        channels_config: ChannelsConfig | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        self.bus = bus
        self.channels_config = channels_config
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace

        self.context = ContextBuilder(workspace)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            brave_api_key=brave_api_key,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
        )

        self._running = False
        self._mcp_servers = mcp_servers or {}
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: dict[str, asyncio.Lock] = {}
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._pending_messages: dict[str, list[InboundMessage]] = {}
        self._debounce_tasks: dict[str, asyncio.Task] = {}
        self._processing_lock = asyncio.Lock()
        self._register_default_tools()
        self._register_workspace_tools()

    @staticmethod
    def _remove_active_task(tasks: dict[str, list[asyncio.Task]], key: str, task: asyncio.Task) -> None:
        bucket = tasks.get(key, [])
        if task in bucket:
            bucket.remove(task)

    async def _cancel_session_tasks(self, session_key: str) -> int:
        """Cancel all active tasks for a session and return cancellation count."""
        tasks = self._active_tasks.pop(session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        sub_cancelled = await self.subagents.cancel_by_session(session_key)
        return cancelled + sub_cancelled

    @classmethod
    def _needs_clarification(cls, text: str) -> bool:
        raw = (text or "").strip()
        if not raw:
            return True
        if "?" in raw or "？" in raw:
            return False
        low = raw.lower()
        if any(hint in low for hint in cls._CONCRETE_HINT_WORDS):
            return False
        if len(raw) <= cls._AMBIGUOUS_SHORT_LEN:
            return True
        return any(re.match(pat, raw, re.IGNORECASE) for pat in cls._AMBIGUOUS_PATTERNS)

    @staticmethod
    def _clarification_message() -> str:
        return (
            "为避免误执行，我先确认下你的意图：\n"
            "1. 你要我做的目标是什么（例如：创建飞书文档/修复某报错/更新某文件）？\n"
            "2. 成功标准是什么（你希望看到什么结果）？\n"
            "3. 现在是否立即执行，还是先给方案再执行？"
        )

    def _merge_pending_messages(self, pending: list[InboundMessage]) -> InboundMessage:
        if len(pending) == 1:
            return pending[0]
        first = pending[0]
        merged_parts = [pending[0].content]
        for i, m in enumerate(pending[1:], start=1):
            merged_parts.append(f"[补充{i}] {m.content}")
        merged_content = "\n\n".join(merged_parts)
        base = pending[-1]
        return replace(base, content=merged_content, media=first.media or base.media)

    async def _flush_session_messages(self, session_key: str) -> None:
        try:
            await asyncio.sleep(self._MERGE_WINDOW_SEC)
            pending = self._pending_messages.pop(session_key, [])
            if not pending:
                return
            merged = self._merge_pending_messages(pending)
            task = asyncio.create_task(self._dispatch(merged))
            self._active_tasks.setdefault(session_key, []).append(task)
            task.add_done_callback(
                lambda t, k=session_key: self._remove_active_task(self._active_tasks, k, t)
            )
        finally:
            self._debounce_tasks.pop(session_key, None)

    async def _queue_inbound_message(self, msg: InboundMessage) -> None:
        session_key = msg.session_key
        self._pending_messages.setdefault(session_key, []).append(msg)
        if old := self._debounce_tasks.get(session_key):
            old.cancel()
        task = asyncio.create_task(self._flush_session_messages(session_key))
        self._debounce_tasks[session_key] = task

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        for cls in (ReadFileTool, WriteFileTool, EditFileTool, ListDirTool):
            self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))
        self.tools.register(ExecTool(
            working_dir=str(self.workspace),
            timeout=self.exec_config.timeout,
            restrict_to_workspace=self.restrict_to_workspace,
            path_append=self.exec_config.path_append,
        ))
        self.tools.register(WebSearchTool(api_key=self.brave_api_key))
        self.tools.register(WebFetchTool())
        self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service:
            self.tools.register(CronTool(self.cron_service))

    def _register_workspace_tools(self) -> None:
        """Load workspace-level tool plugins from {workspace}/tools_init.py."""
        tools_init = self.workspace / "tools_init.py"
        if not tools_init.is_file():
            return
        import importlib.util
        spec = importlib.util.spec_from_file_location("workspace_tools", tools_init)
        if not spec or not spec.loader:
            return
        try:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            register_fn = getattr(mod, "register_tools", None)
            if callable(register_fn):
                register_fn(self)
                logger.info("Loaded workspace tools from {}", tools_init)
        except Exception as e:
            logger.warning("Failed to load workspace tools: {}", e)

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(self._mcp_servers, self.tools, self._mcp_stack)
            self._mcp_connected = True
        except BaseException as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except BaseException:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        for name in ("message", "spawn", "cron"):
            if tool := self.tools.get(name):
                if hasattr(tool, "set_context"):
                    tool.set_context(channel, chat_id, *([message_id] if name == "message" else []))

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _extract_text_tool_calls(text: str, known_tools: set[str]) -> list[tuple[str, dict]]:
        """Extract tool calls that the model wrote as text instead of using function calling API.

        Detects patterns like ``functions.tool_name({...})`` and parses them into
        (name, arguments) pairs.  Only tools present in *known_tools* are considered.
        """
        results: list[tuple[str, dict]] = []
        for m in re.finditer(r'functions\.(\w+)\s*\(', text):
            name = m.group(1)
            if name not in known_tools:
                continue
            start = text.find('{', m.end())
            if start == -1:
                continue
            depth, end = 0, start
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            try:
                args = json.loads(text[start:end])
                results.append((name, args))
            except (json.JSONDecodeError, ValueError):
                continue
        return results

    @classmethod
    def _has_terminal_marker(cls, content: str) -> bool:
        return any(marker in content for marker in cls._TERMINAL_MARKERS)

    @classmethod
    def _strip_terminal_markers(cls, content: str | None) -> str | None:
        if not content:
            return content
        cleaned = content
        for marker in cls._TERMINAL_MARKERS:
            cleaned = cleaned.replace(marker, "")
        return cleaned.strip() or None

    @classmethod
    def _tool_result_limit(cls, tool_name: str | None, content: str) -> int:
        if cls._has_terminal_marker(content):
            return cls._TERMINAL_TOOL_RESULT_MAX_CHARS
        if tool_name in cls._EXTERNAL_API_TOOLS:
            return cls._TERMINAL_TOOL_RESULT_MAX_CHARS
        return cls._TOOL_RESULT_MAX_CHARS

    def _inject_terminal_feedback(
        self,
        messages: list[dict[str, Any]],
        tool_name: str,
        result: str,
        fail_counts: dict[str, int],
    ) -> list[dict[str, Any]]:
        if "[DONE]" in result:
            fail_counts[tool_name] = 0
            messages.append({
                "role": "system",
                "content": (
                    f"Tool '{tool_name}' returned [DONE]. "
                    "Stop calling tools and directly report this result to the user."
                ),
            })
            return messages

        if "[FAILED]" in result:
            if tool_name in self._EXTERNAL_API_TOOLS:
                fail_counts[tool_name] = fail_counts.get(tool_name, 0) + 1
            else:
                fail_counts[tool_name] = fail_counts.get(tool_name, 0)

            if fail_counts.get(tool_name, 0) >= 3:
                messages.append({
                    "role": "system",
                    "content": (
                        f"Tool '{tool_name}' has failed repeatedly. "
                        "Report the error details to the user and wait for instruction. "
                        "Do not retry this tool again in this turn."
                    ),
                })
            else:
                messages.append({
                    "role": "system",
                    "content": (
                        f"Tool '{tool_name}' returned [FAILED]. "
                        "Report the error to the user and do not continue blind retries."
                    ),
                })
            return messages

        fail_counts[tool_name] = 0
        return messages

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages)."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        consecutive_failed_tools: dict[str, int] = {}

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # If provider returned an error (e.g. rate limit after retries),
            # log it and break rather than sending raw error text to user.
            if response.finish_reason == "error":
                logger.error("Provider error: {}", (response.content or "")[:200])
                final_content = "⚠️ 当前模型暂时不可用，请稍后重试。"
                break

            if response.has_tool_calls:
                terminal_response: str | None = None
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        await on_progress(clean)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
                    if isinstance(result, str):
                        messages = self._inject_terminal_feedback(
                            messages, tool_call.name, result, consecutive_failed_tools,
                        )
                        if self._has_terminal_marker(result):
                            terminal_response = self._strip_terminal_markers(result)
                            break

                if terminal_response is not None:
                    final_content = terminal_response
                    break
            else:
                clean = self._strip_think(response.content)

                # Intercept tool calls that the model wrote as text instead of
                # using the function calling API (common with some models).
                text_calls = self._extract_text_tool_calls(
                    clean or "", set(self.tools._tools.keys()),
                )
                if text_calls:
                    terminal_response: str | None = None
                    logger.warning(
                        "Model output {} tool call(s) as text – intercepting",
                        len(text_calls),
                    )
                    tool_call_dicts = []
                    for i, (tc_name, tc_args) in enumerate(text_calls):
                        tool_call_dicts.append({
                            "id": f"text_{iteration}_{i}",
                            "type": "function",
                            "function": {
                                "name": tc_name,
                                "arguments": json.dumps(tc_args, ensure_ascii=False),
                            },
                        })
                    messages = self.context.add_assistant_message(
                        messages, None, tool_call_dicts,
                        reasoning_content=response.reasoning_content,
                    )
                    for tc_dict in tool_call_dicts:
                        fn = tc_dict["function"]
                        fn_name = fn["name"]
                        fn_args = json.loads(fn["arguments"])
                        tools_used.append(fn_name)
                        logger.info("Tool call (from text): {}({})", fn_name, fn["arguments"][:200])
                        result = await self.tools.execute(fn_name, fn_args)
                        messages = self.context.add_tool_result(
                            messages, tc_dict["id"], fn_name, result,
                        )
                        if isinstance(result, str):
                            messages = self._inject_terminal_feedback(
                                messages, fn_name, result, consecutive_failed_tools,
                            )
                            if self._has_terminal_marker(result):
                                terminal_response = self._strip_terminal_markers(result)
                                break

                    if terminal_response is not None:
                        final_content = terminal_response
                        break
                    continue

                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                )
                final_content = self._strip_terminal_markers(clean)
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning("Max iterations ({}) reached", self.max_iterations)
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if msg.content.strip().lower() == "/stop":
                await self._handle_stop(msg)
            else:
                active = [t for t in self._active_tasks.get(msg.session_key, []) if not t.done()]
                if active:
                    cancelled = await self._cancel_session_tasks(msg.session_key)
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"收到补充需求，已打断当前执行（{cancelled} 个任务），合并你的新输入后继续。",
                        metadata=msg.metadata or {},
                    ))
                await self._queue_inbound_message(msg)

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks and subagents for the session."""
        if debounce := self._debounce_tasks.pop(msg.session_key, None):
            debounce.cancel()
        dropped = len(self._pending_messages.pop(msg.session_key, []))
        total = await self._cancel_session_tasks(msg.session_key)
        content = f"⏹ Stopped {total} task(s)." if total else "No active task to stop."
        if dropped:
            content += f" 丢弃待执行补充消息 {dropped} 条。"
        await self.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        async with self._processing_lock:
            try:
                response = await self._process_message(msg)
                if response is not None:
                    await self.bus.publish_outbound(response)
                elif msg.channel == "cli":
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel, chat_id=msg.chat_id,
                        content="", metadata=msg.metadata or {},
                    ))
            except asyncio.CancelledError:
                logger.info("Task cancelled for session {}", msg.session_key)
                raise
            except Exception:
                logger.exception("Error processing message for session {}", msg.session_key)
                await self.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Sorry, I encountered an error.",
                ))

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            history = session.get_history(max_messages=self.memory_window)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content, channel=channel, chat_id=chat_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(messages)
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd = msg.content.strip().lower()
        if cmd == "/new":
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated:]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, archive_all=True):
                            return OutboundMessage(
                                channel=msg.channel, chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)
                if not lock.locked():
                    self._consolidation_locks.pop(session.key, None)

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="🐈 nanobot commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands")

        if self._needs_clarification(msg.content):
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=self._clarification_message(),
                metadata=msg.metadata or {},
            )

        unconsolidated = len(session.messages) - session.last_consolidated
        if (unconsolidated >= self.memory_window and session.key not in self._consolidating):
            self._consolidating.add(session.key)
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session)
                finally:
                    self._consolidating.discard(session.key)
                    if not lock.locked():
                        self._consolidation_locks.pop(session.key, None)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        history = session.get_history(max_messages=self.memory_window)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages, on_progress=on_progress or _bus_progress,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        if (mt := self.tools.get("message")) and isinstance(mt, MessageTool) and mt._sent_in_turn:
            return None

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)
        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime
        for m in messages[skip:]:
            entry = {k: v for k, v in m.items() if k != "reasoning_content"}
            role, content = entry.get("role"), entry.get("content")
            if role == "tool" and isinstance(content, str):
                limit = self._tool_result_limit(entry.get("name"), content)
                if len(content) > limit:
                    entry["content"] = content[:limit] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    continue
                if isinstance(content, list):
                    entry["content"] = [
                        {"type": "text", "text": "[image]"} if (
                            c.get("type") == "image_url"
                            and c.get("image_url", {}).get("url", "").startswith("data:image/")
                        ) else c for c in content
                    ]
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _consolidate_memory(self, session, archive_all: bool = False) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await MemoryStore(self.workspace).consolidate(
            session, self.provider, self.model,
            archive_all=archive_all, memory_window=self.memory_window,
        )

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(msg, session_key=session_key, on_progress=on_progress)
        return response.content if response else ""
