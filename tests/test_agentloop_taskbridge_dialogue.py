import asyncio
from pathlib import Path

import pytest

from core.kylopro_tools import register_kylopro_tools
from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest


class ScriptedMainProvider(LLMProvider):
    def get_default_model(self) -> str:
        return "dummy/main"

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
    ) -> LLMResponse:
        last_user_index = max(i for i, msg in enumerate(messages) if msg.get("role") == "user")
        last_user = messages[last_user_index]
        tool_messages = [msg for msg in messages[last_user_index + 1:] if msg.get("role") == "tool"]
        content = last_user.get("content", "")

        if "启动一个长任务" in content and not tool_messages:
            return LLMResponse(
                content="我会启动后台任务。",
                tool_calls=[
                    ToolCallRequest(
                        id="tc-spawn",
                        name="spawn",
                        arguments={
                            "task": "Analyze a large codebase in the background and keep updating task state.",
                            "label": "Long Task Demo",
                        },
                    )
                ],
            )

        if "现在进度" in content and not tool_messages:
            return LLMResponse(
                content="我先读取当前任务状态。",
                tool_calls=[
                    ToolCallRequest(
                        id="tc-read",
                        name="task_read",
                        arguments={"format": "summary"},
                    )
                ],
            )

        if "停止这个任务" in content and not tool_messages:
            return LLMResponse(
                content="我先写入中断标记。",
                tool_calls=[
                    ToolCallRequest(
                        id="tc-interrupt",
                        name="task_interrupt",
                        arguments={"reason": "user requested stop", "format": "summary"},
                    )
                ],
            )

        if tool_messages:
            last_tool = tool_messages[-1].get("content", "")
            if "现在进度" in content and "status:" in last_tool:
                return LLMResponse(content=f"当前任务状态如下：\n{last_tool}")
            if "停止这个任务" in content and "interrupt_requested: True" in last_tool:
                return LLMResponse(content="已写入停止标记，后台任务会在下一步退出。")
            if "请启动一个长任务" in content and "Subagent" in last_tool:
                return LLMResponse(content="后台任务已经启动，你可以随时问我进度。")

        return LLMResponse(content="对话结束。")


class SlowSubagentProvider(LLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def get_default_model(self) -> str:
        return "dummy/subagent"

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
    ) -> LLMResponse:
        self.calls += 1
        await asyncio.sleep(0.15)
        if self.calls < 5:
            return LLMResponse(content=f"working-{self.calls}", tool_calls=[])
        return LLMResponse(content="subagent finished", tool_calls=[])


async def _wait_for_condition(predicate, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("condition was not met in time")
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_agentloop_dialogue_can_spawn_query_and_interrupt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    bus = MessageBus()
    loop = AgentLoop(
        bus=bus,
        provider=ScriptedMainProvider(),
        workspace=workspace,
        restrict_to_workspace=True,
    )
    register_kylopro_tools(loop)
    loop.subagents.provider = SlowSubagentProvider()
    loop.subagents.model = loop.subagents.provider.get_default_model()

    start_reply = await loop.process_direct("请启动一个长任务")
    assert "后台任务已经启动" in start_reply

    await _wait_for_condition(lambda: loop.subagents.get_running_count() > 0)

    progress_reply = await loop.process_direct("现在进度如何？")
    assert "当前任务状态如下" in progress_reply
    assert "status:" in progress_reply
    assert "Long Task Demo" in progress_reply

    stop_reply = await loop.process_direct("停止这个任务")
    assert "已写入停止标记" in stop_reply

    await _wait_for_condition(lambda: loop.subagents.get_running_count() == 0)

    final_reply = await loop.process_direct("现在进度如何？")
    assert "interrupted" in final_reply
    assert "interrupt_requested: True" in final_reply
