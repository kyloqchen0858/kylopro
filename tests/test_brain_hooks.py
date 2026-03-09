"""BrainHooks 集成测试 — 模拟 AgentLoop 验证 hook 安装"""
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import asyncio

# Setup paths
kylopro_root = Path(__file__).resolve().parent.parent
os.environ.setdefault("KYLOPRO_DIR", str(kylopro_root))
sys.path.insert(0, str(kylopro_root))


def test_brain_context():
    """测试 _build_brain_context 是否能读取 HOT 记忆"""
    from core.brain_hooks import _build_brain_context
    ctx = _build_brain_context()
    print(f"[1] Brain context length: {len(ctx)} chars")
    if ctx:
        print(f"    Preview: {ctx[:200]}")
    else:
        print("    (empty - expected if no HOT memory)")
    return True


def test_patch_system_prompt():
    """测试 build_system_prompt patch"""
    from core.brain_hooks import _patch_system_prompt

    mock_loop = MagicMock()
    original_called = [False]

    def fake_build(skill_names=None):
        original_called[0] = True
        return "# Original System Prompt"

    mock_loop.context.build_system_prompt = fake_build
    _patch_system_prompt(mock_loop)

    result = mock_loop.context.build_system_prompt()
    assert original_called[0], "Original build_system_prompt not called"
    assert "Original System Prompt" in result
    print(f"[2] Patched system prompt length: {len(result)} chars")
    print(f"    Contains brain context: {'KyloBrain' in result}")
    return True


def test_patch_process_message():
    """测试 _process_message patch"""
    from core.brain_hooks import _patch_process_message

    mock_loop = MagicMock()
    call_log = []

    async def fake_process(msg, session_key=None, on_progress=None):
        call_log.append("processed")
        resp = MagicMock()
        resp.content = "测试回复"
        return resp

    mock_loop._process_message = fake_process
    _patch_process_message(mock_loop)

    # Simulate a message
    msg = MagicMock()
    msg.content = "帮我写一个 Python 脚本处理 CSV 文件"
    msg.channel = "cli"

    result = asyncio.get_event_loop().run_until_complete(
        mock_loop._process_message(msg)
    )
    assert "processed" in call_log, "Original _process_message not called"
    assert result.content == "测试回复"
    print(f"[3] Process message hook: OK (response={result.content})")
    return True


def test_lightweight_telegram_ack():
    """测试 Telegram 简短确认不会走重型工具链"""
    from core.brain_hooks import _patch_process_message

    mock_loop = MagicMock()
    call_log = []

    async def fake_process(msg, session_key=None, on_progress=None):
        call_log.append("processed")
        resp = MagicMock()
        resp.content = "不应执行到这里"
        return resp

    mock_loop._process_message = fake_process
    _patch_process_message(mock_loop)

    msg = MagicMock()
    msg.content = "确认"
    msg.channel = "telegram"
    msg.chat_id = "8534144265"
    msg.metadata = {}

    result = asyncio.get_event_loop().run_until_complete(
        mock_loop._process_message(msg)
    )
    assert call_log == [], "Lightweight ack should bypass original _process_message"
    assert "脑体链路在线" in result.content
    print(f"[4] Lightweight ack bypass: OK (response={result.content})")
    return True


def test_auto_record_episode():
    """测试自动 episode 记录"""
    from core.brain_hooks import _auto_record_episode

    # 这应该静默写入 WARM 层
    _auto_record_episode(
        task="帮我写一个 Python 脚本",
        response="好的，这里是脚本...",
        duration=2.5,
        channel="cli",
    )
    print("[5] Auto-record episode: OK (no exception)")

    # 验证 WARM 层有记录
    from skills.kylobrain.kylobrain_connector import get_connector
    conn = get_connector()
    if conn and conn.brain:
        episodes = conn.brain.warm.read_all("episodes")
        auto_eps = [e for e in episodes if e.get("source") == "auto_hook"]
        print(f"    Auto-hook episodes in WARM: {len(auto_eps)}")
    return True


def test_install_full():
    """测试完整 install_brain_hooks"""
    from core.brain_hooks import install_brain_hooks

    mock_loop = MagicMock()
    mock_loop.context.build_system_prompt = MagicMock(return_value="# test")

    async def fake_process(msg, session_key=None, on_progress=None):
        resp = MagicMock()
        resp.content = "ok"
        return resp

    mock_loop._process_message = fake_process

    install_brain_hooks(mock_loop)
    print("[6] install_brain_hooks: OK (no exception)")
    return True


if __name__ == "__main__":
    print("=" * 50)
    print("BrainHooks 集成测试")
    print("=" * 50)

    tests = [
        test_brain_context,
        test_patch_system_prompt,
        test_patch_process_message,
        test_lightweight_telegram_ack,
        test_auto_record_episode,
        test_install_full,
    ]

    passed = 0
    for t in tests:
        try:
            if t():
                passed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")

    print(f"\n{'=' * 50}")
    print(f"Result: {passed}/{len(tests)} passed")
    print("=" * 50)
