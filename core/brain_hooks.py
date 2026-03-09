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
from collections import defaultdict
from pathlib import Path

from loguru import logger

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


_RETRY_STATE: dict[str, dict] = defaultdict(lambda: {
    "retry_count": 0,
    "task_goal": "",
    "fix_history": [],
})
MAX_RETRIES = 3

CHAT_MODEL = "deepseek/deepseek-chat"
REASONER_MODEL = "deepseek/deepseek-reasoner"

_HIGH_COMPLEXITY_HINTS = (
    "根因", "架构", "设计", "多步", "规划", "方案", "重构", "优化策略", "算法",
    "并发", "一致性", "复杂", "诊断", "系统性", "tradeoff", "failure mode", "postmortem",
)


def _estimate_complexity(user_input: str) -> str:
    """Rule-based complexity estimator: low/medium/high."""
    text = (user_input or "").strip().lower()
    if not text:
        return "low"

    score = 0
    if len(text) > 120:
        score += 1
    if len(text) > 220:
        score += 1

    if re.search(r"\n\s*\d+\.|步骤|step|阶段|phase", text):
        score += 1

    for kw in _HIGH_COMPLEXITY_HINTS:
        if kw in text:
            score += 1

    if score >= 3:
        return "high"
    if score == 2:
        return "medium"
    return "low"


def _route_task(user_input: str) -> tuple[str, str]:
    """Route to ask_user / deepseek-v3.2 / deepseek-r1."""
    if _is_ambiguous_instruction(user_input):
        return "ask_user", "instruction_ambiguous"

    complexity = _estimate_complexity(user_input)
    if complexity == "high":
        return "deepseek-r1", "high_complexity"
    return "deepseek-v3.2", f"{complexity}_complexity"


def _is_ambiguous_instruction(text: str) -> bool:
    """只拦截真正无法处理的空消息，其他全部交给 LLM 自然判断。"""
    t = (text or "").strip()
    # 只有完全空消息或纯标点才算 ambiguous
    if not t:
        return True
    stripped = re.sub(r"[^\w]", "", t)
    return len(stripped) == 0


def _build_clarification_question(user_input: str) -> str:
    return f"你刚才发了：「{user_input}」——具体想做什么？"


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
    """从 KyloBrain 提取 HOT 记忆 + WARM 近期经验 + 失败预警，构建 prompt 片段。"""
    conn = _get_connector()
    if not conn or not conn.brain:
        return ""

    parts = []

    # HOT 记忆摘要（MEMORY.md 重点内容）
    try:
        hot_text = conn.brain.hot.read()
        if hot_text.strip():
            lines = [l.strip() for l in hot_text.strip().split("\n") if l.strip()]
            recent = lines[-5:] if len(lines) > 5 else lines
            parts.append("## 🧠 KyloBrain · 近期记忆\n" + "\n".join(f"- {l[:120]}" for l in recent))
    except Exception:
        pass

    # WARM 层近期经验回忆（P0 修复：读取端接通）
    try:
        recent_episodes = conn.brain.warm.read_recent("episodes", days=3)
        if recent_episodes:
            # 提取最近 5 条，只保留关键信息
            last_eps = recent_episodes[-5:]
            ep_lines = []
            for ep in last_eps:
                task = ep.get("task", "")[:60]
                success = "✅" if ep.get("success") else "❌"
                outcome = ep.get("outcome", "")[:80]
                ep_lines.append(f"  {success} {task} → {outcome}")
            parts.append("## 📋 近期经验（WARM 层）\n" + "\n".join(ep_lines))

        # 近期失败记录
        recent_failures = conn.brain.warm.read_recent("failures", days=7)
        if recent_failures:
            last_fails = recent_failures[-3:]
            fail_lines = []
            for f in last_fails:
                task = f.get("task", "")[:50]
                error = f.get("error", "")[:60]
                recovery = f.get("recovery", "")[:60]
                fail_lines.append(f"  ❌ {task}: {error} → 修复: {recovery}")
            parts.append("## ⚠️ 近期失败模式\n" + "\n".join(fail_lines))

        # 能力域成功率
        patterns = conn.brain.warm.read_all("patterns")
        if patterns:
            pat_lines = []
            for p in sorted(patterns, key=lambda x: x.get("sample_count", 0), reverse=True)[:5]:
                task_type = p.get("task_type", "")
                rate = p.get("success_rate", 0)
                count = p.get("sample_count", 0)
                pat_lines.append(f"  {task_type}: {rate:.0%} ({count}次)")
            parts.append("## 📊 能力成功率\n" + "\n".join(pat_lines))
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

    # L2 身份认知（如果存在）
    try:
        identity_path = Path(conn.brain.dir).parent.parent / "data" / "memory" / "L2_identity" / "current" / "identity_statement.md"
        if identity_path.exists():
            identity_text = identity_path.read_text(encoding="utf-8").strip()
            if identity_text:
                # 取前 500 字符
                parts.append("## 🪞 自我认知\n" + identity_text[:500])
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
            "feishu", "oauth2_vault", "web_search",
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
        ])

    # 降级路径提醒
    lines.extend([
        "",
        "⚡ 工具降级规则（必读）：",
        "- 一个工具失败 ≠ 任务失败，立即走备选链",
        "- screen 失败 → exec 命令行 → python 脚本 → 通知用户",
        "- feishu 失败 → 检查token → refresh → curl直调 → 本地保存+通知",
        "- deep_think 失败 → 降级到 chat → local_think → 分步推理",
        "- exec 失败 → python等效实现 → 检查权限",
        "- spawn 失败 → 当前上下文执行 → 拆分小步骤",
        "- 所有备选耗尽时：告诉用户已尝试了什么、建议手动操作步骤",
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
        bridge = getattr(getattr(agent_loop, "subagents", None), "task_bridge", None)

        route, route_reason = _route_task(getattr(msg, "content", ""))
        original_model = agent_loop.model

        if route == "deepseek-r1":
            agent_loop.model = REASONER_MODEL
        else:
            # Keep day-to-day loop on v3.2 chat model unless explicitly escalated.
            agent_loop.model = CHAT_MODEL

        if bridge:
            bridge.write_state(
                append_history=f"Route selected: {route} ({route_reason})",
                metadata={"route": route, "route_reason": route_reason},
            )
        try:
            if route == "ask_user":
                q = _build_clarification_question(msg.content)
                if bridge:
                    bridge.write_state(
                        status="waiting_clarification",
                        summary="等待用户澄清",
                        clarification_pending=True,
                        clarification_question=q,
                        append_history="Instruction ambiguous; clarification requested.",
                    )
                conn = _get_connector()
                if conn:
                    try:
                        conn.record_preference("clarification_request", msg.content[:120], source="pre_message_hook")
                    except Exception:
                        pass
                from nanobot.bus.events import OutboundMessage
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=f"❓ {q}",
                    metadata=msg.metadata or {},
                )

            if bridge:
                # 用户补充后自动解除澄清挂起
                bridge.write_state(
                    clarification_pending=False,
                    clarification_question="",
                    append_history="Clarification received; continue execution.",
                )

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

            # 调用原始方法（按路由后的模型执行）
            response = await original(msg, session_key=session_key, on_progress=on_progress)

            # post_tool 失败循环控制：达到上限后请求人工介入
            key = session_key or getattr(msg, "session_key", "") or f"{msg.channel}:{msg.chat_id}"
            state = _RETRY_STATE[key]
            content = response.content if response and response.content else ""
            if "❌" in content or "Error" in content:
                state["retry_count"] += 1
                state["task_goal"] = state["task_goal"] or task_preview
                state["fix_history"].append({
                    "ts": time.time(),
                    "error": content[:300],
                })
                if bridge:
                    bridge.write_state(
                        append_fix={
                            "ts": time.time(),
                            "error": content[:300],
                            "analysis": "pending_deep_analysis",
                        },
                        append_history=f"Auto-fix attempt failed #{state['retry_count']}",
                    )

                conn = _get_connector()
                if conn:
                    try:
                        conn.record_failure(
                            error_type="tool_error",
                            task=state["task_goal"][:120],
                            fix="auto_retry",
                            success=False,
                        )
                    except Exception:
                        pass

                if state["retry_count"] >= MAX_RETRIES:
                    from nanobot.bus.events import OutboundMessage
                    manual = (
                        "⚠️ 连续修正已达到上限（3次）。\n"
                        "请人工确认下一步：\n"
                        "1) 提供更精确目标\n"
                        "2) 允许我按 deep_think 方案重构\n"
                        "3) 暂停并归档该任务"
                    )
                    if bridge:
                        bridge.write_state(
                            status="needs_human_intervention",
                            summary="连续失败达到上限，等待人工介入",
                            append_history="Escalated to human after max retries.",
                        )
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=manual,
                        metadata=msg.metadata or {},
                    )
            else:
                state["retry_count"] = 0
                state["fix_history"] = []

            # 自动记录 episode（静默，不阻塞响应）
            try:
                _auto_record_episode(
                    task=task_preview,
                    response=response.content[:200] if response and response.content else "",
                    duration=time.time() - t0,
                    channel=msg.channel,
                    route=route,
                )
            except Exception as e:
                logger.debug("BrainHooks auto-record failed: {}", e)

            return response
        finally:
            # 恢复默认模型，避免污染后续会话
            agent_loop.model = original_model

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


def _auto_record_episode(task: str, response: str, duration: float, channel: str, route: str = "") -> None:
    """将一轮对话静默写入 WARM 层 episodes + L0 结构化记录。"""
    conn = _get_connector()

    # 跳过系统命令和极短消息
    if not task or task.startswith("/") or len(task.strip()) < 5:
        return

    # 智能判定成功/失败，而非盲目标 True
    success = _infer_episode_success(response)

    # --- WARM 层写入（保持兼容） ---
    if conn and conn.brain:
        task_id = f"auto_{hashlib.md5(f'{task}{time.time()}'.encode()).hexdigest()[:8]}"
        conn.brain.warm.append("episodes", {
            "task_id": task_id,
            "task": task[:200],
            "outcome": response[:200] if response else "(no response)",
            "success": success,
            "duration_sec": round(duration, 1),
            "channel": channel,
            "route": route,
            "source": "auto_hook",
            "ts": time.time(),
        })

    # --- L0 结构化写入 ---
    try:
        from core.memory.l0_writer import write_episode as l0_write

        # 推断任务类型
        task_lower = task.lower()
        if "feishu" in task_lower or "飞书" in task_lower:
            task_type = "feishu_workflow"
        elif "freelance" in task_lower or "接单" in task_lower:
            task_type = "freelance"
        elif any(k in task_lower for k in ("code", "debug", "fix", "test", "代码", "修复")):
            task_type = "coding"
        elif any(k in task_lower for k in ("文档", "doc", "write", "读", "阅读")):
            task_type = "document"
        else:
            task_type = "general"

        l0_write(
            task_summary=task,
            task_type=task_type,
            source=channel,
            success=success,
            duration_sec=duration,
            outcome=response[:200] if response else "",
            route=route,
        )
    except Exception as e:
        logger.debug("L0 write failed (non-blocking): {}", e)


# ── 失败信号关键词 ────────────────────────────────────────────
_FAILURE_SIGNALS = (
    "❌", "失败", "错误", "不可用", "暂时不可用", "不存在", "Error",
    "error", "failed", "not found", "404", "403", "500",
    "timeout", "超时", "无法", "拒绝", "exception", "异常",
    "reached the maximum", "tool call iterations",
)

_FALSE_POSITIVE_GUARDS = (
    "✅", "已创建", "已发送", "成功", "已完成", "success",
)


def _infer_episode_success(response: str) -> bool:
    """从回复内容推断本轮是否真正成功。"""
    if not response:
        return False
    text = response[:500]
    # 如果同时包含成功和失败信号，看哪个更靠前（通常结论在前面）
    has_fail = any(sig in text for sig in _FAILURE_SIGNALS)
    has_success = any(sig in text for sig in _FALSE_POSITIVE_GUARDS)
    if has_fail and not has_success:
        return False
    if has_success and not has_fail:
        return True
    if has_fail and has_success:
        # 找第一个信号的位置，靠前的权重更大
        first_fail = min((text.find(s) for s in _FAILURE_SIGNALS if s in text), default=9999)
        first_success = min((text.find(s) for s in _FALSE_POSITIVE_GUARDS if s in text), default=9999)
        return first_success < first_fail
    # 默认成功（普通对话大概率是正常的）
    return True
