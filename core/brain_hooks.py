"""
KyloBrain · BrainHooks
======================
自动将 KyloBrain 注入 nanobot AgentLoop 的消息处理管线。

注入点：
  1. build_system_prompt → 追加 HOT 记忆摘要到系统 prompt
  2. _process_message    → 任务后自动记录 episode 到 WARM 层

通过 tools_init.py 调用 install_brain_hooks(agent_loop) 完成安装。
零 nanobot 核心代码修改。
"""

from __future__ import annotations

import hashlib
import re
import sys
import time
from pathlib import Path

from loguru import logger

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def _get_connector():
    """Lazy-load KyloConnector singleton."""
    try:
        from skills.kylobrain.kylobrain_connector import get_connector
        return get_connector()
    except Exception as e:
        logger.debug("BrainHooks: connector unavailable: {}", e)
        return None


def install_brain_hooks(agent_loop) -> None:
    """
    Monkey-patch AgentLoop to inject KyloBrain context and auto-recording.

    Safe: if brain fails, original behavior is preserved.
    """
    _patch_system_prompt(agent_loop)
    _patch_process_message(agent_loop)
    logger.info("BrainHooks installed")


# ═══════════════════════════════════════════
# Hook 1: 系统 prompt 注入 HOT 记忆
# ═══════════════════════════════════════════

def _patch_system_prompt(agent_loop) -> None:
    """Wrap ContextBuilder.build_system_prompt to append brain context."""
    original = agent_loop.context.build_system_prompt

    def _patched_build_system_prompt(skill_names=None):
        prompt = original(skill_names)
        extra_parts = []
        brain_ctx = _build_brain_context()
        body_ctx = _build_body_context(agent_loop)
        self_ctx = _build_self_context(agent_loop)
        if brain_ctx:
            extra_parts.append(brain_ctx)
        if body_ctx:
            extra_parts.append(body_ctx)
        if self_ctx:
            extra_parts.append(self_ctx)
        if extra_parts:
            prompt += "\n\n---\n\n" + "\n\n---\n\n".join(extra_parts)
        return prompt

    agent_loop.context.build_system_prompt = _patched_build_system_prompt


def _build_brain_context() -> str:
    """从 KyloBrain 提取 HOT 记忆和近期模式，构建 prompt 片段。"""
    conn = _get_connector()
    if not conn or not conn.brain:
        return ""

    parts = []

    # HOT 记忆摘要（MEMORY.md 重点内容）
    try:
        hot_text = conn.brain.hot.read()
        if hot_text.strip():
            # 取最近几行
            lines = [l.strip() for l in hot_text.strip().split("\n") if l.strip()]
            recent = lines[-5:] if len(lines) > 5 else lines
            parts.append("## 🧠 KyloBrain · 近期记忆\n" + "\n".join(f"- {l[:120]}" for l in recent))
    except Exception:
        pass

    # 近期失败模式（布隆过滤器的文本回顾）
    try:
        bloom_count = sum(conn.algos.bloom.bits)
        if conn.algos and bloom_count > 0:
            parts.append(f"⚠️ 布隆过滤器已记录 {bloom_count} 个失败特征位，"
                         "使用 kylobrain(action='pre_task') 可获取具体预警。")
    except Exception:
        pass

    # 技能图：最近工作流
    try:
        if conn.algos and conn.algos.graph.graph:
            top_skills = sorted(
                conn.algos.graph.graph.items(),
                key=lambda kv: sum(kv[1].values()),
                reverse=True,
            )[:3]
            if top_skills:
                skill_text = ", ".join(f"{s[0]}({sum(s[1].values())}次)" for s in top_skills)
                parts.append(f"🗺️ 擅长领域: {skill_text}")
    except Exception:
        pass

    return "\n\n".join(parts)


def _build_body_context(agent_loop) -> str:
    """Describe Kylo's runtime skeleton and limbs from the live workspace."""
    try:
        tool_names = sorted(agent_loop.tools._tools.keys())
    except Exception:
        tool_names = []

    key_limbs = [
        name for name in (
            "read_file", "write_file", "edit_file", "list_dir", "exec",
            "task_inbox", "task_read", "task_write", "task_interrupt",
            "deep_think", "local_think", "screen", "spawn", "cron", "kylobrain",
        )
        if name in tool_names
    ]

    skeleton = [
        "- core/: runtime wiring, BrainHooks, custom tools",
        "- kylo_tools/: TaskBridge shared state and execution joints",
        "- skills/: operating manuals and always-on capabilities",
        "- brain/: HOT/WARM/COLD memory and action logs",
        "- tasks/: inbox, pending work, active task state",
        "- docs/: architecture, reports, roadmap",
        "- data/: local config, finance, state snapshots",
    ]

    lines = [
        "## KyloBody · 骨架与四肢",
        "你当前运行在 Kylopro-Nexus 根目录，不是旧的 workspace/ 子目录。",
        "骨架：",
        *skeleton,
    ]
    if key_limbs:
        lines.extend([
            "",
            "四肢（当前可直接调动的关键执行器）：",
            "- " + ", ".join(key_limbs),
            "",
            "协同规则：先用大脑(kylobrain/deep_think/local_think)判断，再用身体(read/write/exec/screen/task_*)执行，长任务交给 spawn + TaskBridge。",
        ])
    return "\n".join(lines)


def _build_self_context(agent_loop) -> str:
    """Persist and inject Kylo's self-model so new capabilities become self-knowledge."""
    conn = _get_connector()
    if not conn or not getattr(conn, "self_model", None):
        return ""
    try:
        tool_names = sorted(agent_loop.tools._tools.keys())
    except Exception:
        tool_names = []
    try:
        conn.refresh_self_model(tool_names=tool_names, workspace=str(agent_loop.workspace))
        return conn.self_model.prompt_context()
    except Exception as e:
        logger.debug("BrainHooks self-model update failed: {}", e)
        return ""


# ═══════════════════════════════════════════
# Hook 2: 消息后自动记录 episode
# ═══════════════════════════════════════════

def _patch_process_message(agent_loop) -> None:
    """Wrap _process_message to auto-record turns as brain episodes."""
    original = agent_loop._process_message

    async def _patched_process_message(msg, session_key=None, on_progress=None):
        quick_reply = _match_lightweight_ack(msg)
        if quick_reply is not None:
            from nanobot.bus.events import OutboundMessage
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=quick_reply,
                metadata=msg.metadata or {},
            )

        # 记录开始时间
        t0 = time.time()
        task_preview = msg.content[:80] if msg.content else ""

        # 调用原始方法
        response = await original(msg, session_key=session_key, on_progress=on_progress)

        # 自动记录 episode（静默，不阻塞响应）
        try:
            _auto_record_episode(
                task=task_preview,
                response=response.content[:200] if response and response.content else "",
                duration=time.time() - t0,
                channel=msg.channel,
            )
        except Exception as e:
            logger.debug("BrainHooks auto-record failed: {}", e)

        return response

    agent_loop._process_message = _patched_process_message


def _match_lightweight_ack(msg) -> str | None:
    """Short-circuit trivial Telegram acknowledgements to avoid heavy tool chains."""
    channel = getattr(msg, "channel", "")
    content = (getattr(msg, "content", "") or "").strip()
    if channel != "telegram" or not content:
        return None

    normalized = re.sub(r"\s+", "", content.lower())
    normalized = normalized.strip(".,!?~`'\"，。！？、")

    ack_responses = {
        "确认": "已收到，脑体链路在线。",
        "收到": "已收到，脑体链路在线。",
        "好的": "收到，当前 gateway 和 BrainHooks 都在线。",
        "好": "收到，当前 gateway 和 BrainHooks 都在线。",
        "ok": "收到，当前 gateway 和 BrainHooks 都在线。",
        "okay": "收到，当前 gateway 和 BrainHooks 都在线。",
        "1": "已记录，继续执行。",
        "2": "已记录，继续执行。",
        "在吗": "在，当前在线。",
        "你好": "你好，当前在线。",
        "脑体确认2": "已确认：脑体链路在线，工具层已接通。",
    }
    if normalized in ack_responses:
        return ack_responses[normalized]

    if len(normalized) <= 4 and normalized in {"嗯", "恩", "行", "可", "在", "在的"}:
        return "收到，当前在线。"

    return None


def _auto_record_episode(task: str, response: str, duration: float, channel: str) -> None:
    """将一轮对话静默写入 WARM 层 episodes。"""
    conn = _get_connector()
    if not conn or not conn.brain:
        return

    # 跳过系统命令和极短消息
    if not task or task.startswith("/") or len(task.strip()) < 5:
        return

    # 生成简短任务 ID
    task_id = f"auto_{hashlib.md5(f'{task}{time.time()}'.encode()).hexdigest()[:8]}"

    # 写入 WARM 层 episodes
    conn.brain.warm.append("episodes", {
        "task_id": task_id,
        "task": task[:200],
        "outcome": response[:200] if response else "(no response)",
        "success": True,  # 自动记录默认成功，失败由显式 post_task 覆盖
        "duration_sec": round(duration, 1),
        "channel": channel,
        "source": "auto_hook",
        "ts": time.time(),
    })
