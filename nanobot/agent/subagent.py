"""Subagent manager for background task execution."""

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.filesystem import ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.web import WebSearchTool, WebFetchTool


class SubagentManager:
    """Manages background subagent execution."""
    
    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        brave_api_key: str | None = None,
        exec_config: "ExecToolConfig | None" = None,
        restrict_to_workspace: bool = False,
    ):
        from nanobot.config.schema import ExecToolConfig
        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self.model = model or provider.get_default_model()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._session_tasks: dict[str, set[str]] = {}  # session_key -> {task_id, ...}
        self.task_bridge = None
    
    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
        session_key: str | None = None,
    ) -> str:
        """Spawn a subagent to execute a task in the background."""
        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        origin = {"channel": origin_channel, "chat_id": origin_chat_id}

        self._write_task_state(
            reset=True,
            task_id=task_id,
            title=display_label,
            status="queued",
            owner="subagent",
            progress=0,
            current_step="queued",
            summary=f"Queued background task: {display_label}",
            detail=task,
            max_iterations=15,
            append_history="Subagent task queued",
            clear_interrupt=True,
        )

        bg_task = asyncio.create_task(
            self._run_subagent(task_id, task, display_label, origin)
        )
        self._running_tasks[task_id] = bg_task
        if session_key:
            self._session_tasks.setdefault(session_key, set()).add(task_id)

        def _cleanup(_: asyncio.Task) -> None:
            self._running_tasks.pop(task_id, None)
            if session_key and (ids := self._session_tasks.get(session_key)):
                ids.discard(task_id)
                if not ids:
                    del self._session_tasks[session_key]

        bg_task.add_done_callback(_cleanup)
        
        logger.info("Spawned subagent [{}]: {}", task_id, display_label)
        return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."
    
    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
    ) -> None:
        """Execute the subagent task and announce the result."""
        logger.info("Subagent [{}] starting task: {}", task_id, label)
        self._write_task_state(
            task_id=task_id,
            title=label,
            status="running",
            owner="subagent",
            progress=5,
            current_step="starting",
            summary=f"Background task running: {label}",
            detail=task,
            append_history="Subagent started",
        )
        
        try:
            # Build subagent tools (no message tool, no spawn tool)
            tools = ToolRegistry()
            allowed_dir = self.workspace if self.restrict_to_workspace else None
            tools.register(ReadFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(WriteFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(EditFileTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(ListDirTool(workspace=self.workspace, allowed_dir=allowed_dir))
            tools.register(ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
                path_append=self.exec_config.path_append,
            ))
            tools.register(WebSearchTool(api_key=self.brave_api_key))
            tools.register(WebFetchTool())
            
            # Build messages with subagent-specific prompt
            system_prompt = self._build_subagent_prompt(task)
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]
            
            # Run agent loop (limited iterations)
            max_iterations = 15
            iteration = 0
            final_result: str | None = None
            
            while iteration < max_iterations:
                if self._interrupt_requested():
                    final_result = "Task interrupted after receiving interrupt flag from main agent."
                    self._write_task_state(
                        status="interrupted",
                        current_step="stopping",
                        summary=f"Task interrupted: {label}",
                        detail=final_result,
                        append_history="Interrupt flag detected by subagent",
                    )
                    await self._announce_result(task_id, label, task, final_result, origin, "interrupted")
                    return

                iteration += 1
                self._write_task_state(
                    status="running",
                    progress=min(95, max(5, int(iteration / max_iterations * 100))),
                    current_step=f"iteration {iteration}",
                    summary=f"Background task running: {label}",
                )
                
                response = await self.provider.chat(
                    messages=messages,
                    tools=tools.get_definitions(),
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )

                if response.finish_reason == "error":
                    logger.error("Subagent [{}] provider error: {}", task_id, (response.content or "")[:200])
                    final_result = "Task failed: model temporarily unavailable."
                    break

                if response.has_tool_calls:
                    # Add assistant message with tool calls
                    tool_call_dicts = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in response.tool_calls
                    ]
                    messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": tool_call_dicts,
                    })
                    
                    # Execute tools
                    for tool_call in response.tool_calls:
                        args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                        logger.debug("Subagent [{}] executing: {} with arguments: {}", task_id, tool_call.name, args_str)
                        result = await tools.execute(tool_call.name, tool_call.arguments)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.name,
                            "content": result,
                        })
                else:
                    # Intercept tool calls written as text (same as AgentLoop)
                    from nanobot.agent.loop import AgentLoop
                    text_calls = AgentLoop._extract_text_tool_calls(
                        response.content or "", set(tools._tools.keys()),
                    )
                    if text_calls:
                        logger.warning("Subagent [{}] model output {} tool call(s) as text – intercepting", task_id, len(text_calls))
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
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": tool_call_dicts,
                        })
                        for tc_dict in tool_call_dicts:
                            fn = tc_dict["function"]
                            fn_name = fn["name"]
                            fn_args = json.loads(fn["arguments"])
                            logger.debug("Subagent [{}] executing (from text): {} with arguments: {}", task_id, fn_name, fn["arguments"])
                            result = await tools.execute(fn_name, fn_args)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc_dict["id"],
                                "name": fn_name,
                                "content": result,
                            })
                        continue

                    final_result = response.content
                    break
            
            if final_result is None:
                final_result = "Task completed but no final response was generated."
            
            logger.info("Subagent [{}] completed successfully", task_id)
            self._write_task_state(
                status="completed",
                progress=100,
                current_step="completed",
                summary=f"Task completed: {label}",
                detail=final_result[:2000],
                append_history="Subagent completed successfully",
            )
            await self._announce_result(task_id, label, task, final_result, origin, "ok")
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error("Subagent [{}] failed: {}", task_id, e)
            self._write_task_state(
                status="failed",
                current_step="failed",
                summary=f"Task failed: {label}",
                detail=error_msg,
                append_history=f"Subagent failed: {str(e)}",
            )
            await self._announce_result(task_id, label, task, error_msg, origin, "error")
    
    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        """Announce the subagent result to the main agent via the message bus."""
        status_text = {
            "ok": "completed successfully",
            "error": "failed",
            "interrupted": "was interrupted",
        }.get(status, status)
        
        announce_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""
        
        # Inject as system message to trigger main agent
        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
        )
        
        await self.bus.publish_inbound(msg)
        logger.debug("Subagent [{}] announced result to {}:{}", task_id, origin['channel'], origin['chat_id'])
    
    def _build_subagent_prompt(self, task: str) -> str:
        """Build a focused system prompt for the subagent."""
        from datetime import datetime
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"

        return f"""# Subagent

## Current Time
{now} ({tz})

You are a subagent spawned by the main agent to complete a specific task.

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings

## What You Can Do
- Read and write files in the workspace
- Execute shell commands
- Search the web and fetch web pages
- Complete the task thoroughly

## What You Cannot Do
- Send messages directly to users (no message tool available)
- Spawn other subagents
- Access the main agent's conversation history

## Workspace
Your workspace is at: {self.workspace}
Skills are available at: {self.workspace}/skills/ (read SKILL.md files as needed)

When you have completed the task, provide a clear summary of your findings or actions."""

    def _get_task_bridge(self):
        bridge = getattr(self, "task_bridge", None)
        if bridge and hasattr(bridge, "read_state") and hasattr(bridge, "write_state"):
            return bridge
        return None

    def _write_task_state(self, **kwargs: Any) -> None:
        bridge = self._get_task_bridge()
        if bridge is None:
            return
        try:
            bridge.write_state(**kwargs)
        except Exception as e:
            logger.debug("TaskBridge write failed: {}", e)

    def _interrupt_requested(self) -> bool:
        bridge = self._get_task_bridge()
        if bridge is None:
            return False
        try:
            return bool(bridge.read_state().get("interrupt_requested"))
        except Exception as e:
            logger.debug("TaskBridge read failed: {}", e)
            return False
    
    async def cancel_by_session(self, session_key: str) -> int:
        """Cancel all subagents for the given session. Returns count cancelled."""
        tasks = [self._running_tasks[tid] for tid in self._session_tasks.get(session_key, [])
                 if tid in self._running_tasks and not self._running_tasks[tid].done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(tasks)

    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self._running_tasks)
