import asyncio
from pathlib import Path

from kylo_tools.task_bridge import TaskBridge
from nanobot.agent.subagent import SubagentManager


class DummyResponse:
    def __init__(self, has_tool_calls: bool, content: str, tool_calls=None):
        self.has_tool_calls = has_tool_calls
        self.content = content
        self.tool_calls = tool_calls or []
        self.reasoning_content = None


class SlowProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_default_model(self) -> str:
        return "dummy/model"

    async def chat(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(0.15)
        if self.calls < 3:
            return DummyResponse(True, f"loop-{self.calls}", [])
        return DummyResponse(False, "done", [])


class DummyBus:
    def __init__(self) -> None:
        self.messages = []

    async def publish_inbound(self, msg) -> None:
        self.messages.append(msg)


async def _wait_until_idle(manager: SubagentManager, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while manager.get_running_count() > 0:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("subagent did not stop in time")
        await asyncio.sleep(0.05)


async def test_spawn_progress_query_and_interrupt(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    provider = SlowProvider()
    bus = DummyBus()
    manager = SubagentManager(
        provider=provider,
        workspace=workspace,
        bus=bus,
        restrict_to_workspace=True,
    )
    bridge = TaskBridge(workspace)
    manager.task_bridge = bridge

    start_message = await manager.spawn(
        "Process a long-running file analysis task in the background.",
        label="Long Task Demo",
    )

    assert "started" in start_message.lower()

    await asyncio.sleep(0.05)
    running_state = bridge.read_state()
    assert running_state["status"] in {"queued", "running"}
    assert running_state["title"] == "Long Task Demo"
    assert running_state["owner"] == "subagent"

    bridge.interrupt("user requested stop")
    await _wait_until_idle(manager)

    final_state = bridge.read_state()
    assert final_state["status"] == "interrupted"
    assert final_state["interrupt_requested"] is True
    assert final_state["interrupt_reason"] == "user requested stop"
    assert "interrupted" in final_state["summary"].lower()
    assert bus.messages
