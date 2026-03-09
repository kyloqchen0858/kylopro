"""
KyloBrain · SelfModel
=====================
Kylo 对自身能力、骨架、四肢、协同方式的认知层。

目标：
  1. 让 Kylo 在 prompt 中始终知道“自己现在能做什么”。
  2. 让开发阶段的新能力和状态变化写入自知层，而不是只留在路线图或聊天里。
  3. 把“脑-身体-骨架协同优先”固化为第一原则。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


BASE_DIR = Path(os.environ.get("KYLOPRO_DIR", Path.home() / "Kylopro-Nexus"))
BRAIN_DIR = BASE_DIR / "brain"
SELF_MODEL_FILE = BRAIN_DIR / "self_model.json"
SELF_UPDATES_FILE = BRAIN_DIR / "self_updates.jsonl"


class SelfModel:
    """Persistent self-cognition store for Kylo."""

    def __init__(self) -> None:
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict:
        if not SELF_MODEL_FILE.exists():
            return {}
        try:
            return json.loads(SELF_MODEL_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def write(self, data: dict) -> None:
        SELF_MODEL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def refresh(self, brain_status: dict | None = None, tool_names: list[str] | None = None, workspace: str = "") -> dict:
        tool_names = sorted(tool_names or [])
        brain_status = brain_status or {}

        # ── 四肢：按能力域分组，标记在线/离线 ──
        capability_domains = {
            "文件操作": {
                "tools": ["read_file", "write_file", "edit_file", "list_dir"],
                "fallback": "所有文件操作均可通过 exec 命令行完成",
            },
            "任务管理": {
                "tools": ["task_inbox", "task_read", "task_write", "task_interrupt"],
                "fallback": "直接读写 tasks/ 目录文件",
            },
            "GUI/屏幕": {
                "tools": ["screen"],
                "fallback": "exec 命令行 → python webbrowser/pyautogui → 通知用户手动操作",
            },
            "命令执行": {
                "tools": ["exec"],
                "fallback": "拆分为 python 脚本后 exec python -c",
            },
            "深度推理": {
                "tools": ["deep_think", "local_think", "kylobrain"],
                "fallback": "降级到当前模型分步推理；kylobrain HOT 层文本搜索",
            },
            "子Agent": {
                "tools": ["spawn"],
                "fallback": "当前上下文直接执行 → task_inbox 分步",
            },
            "定时任务": {
                "tools": ["cron"],
                "fallback": "exec schtasks → 写 .bat 脚本 → task_inbox 提醒",
            },
            "外部平台": {
                "tools": ["feishu", "oauth2_vault", "web_search"],
                "fallback": "oauth2_vault refresh → exec curl → 降级为本地文件 + 通知用户",
            },
        }

        limbs_detail = []
        for domain, info in capability_domains.items():
            online = [t for t in info["tools"] if t in tool_names]
            offline = [t for t in info["tools"] if t not in tool_names]
            limbs_detail.append({
                "domain": domain,
                "online": online,
                "offline": offline,
                "fallback": info["fallback"],
            })

        cognition = {
            "identity": {
                "name": "Kylo",
                "workspace": workspace or str(BASE_DIR),
                "language_priority": "中文优先",
                "coordination_priority": "脑和手脚和协调，身体和骨架的协调第一位",
            },
            "skeleton": [
                "core/",
                "kylo_tools/",
                "skills/",
                "brain/",
                "tasks/",
                "docs/",
                "data/",
            ],
            "brain": {
                "analyze": [name for name in ("kylobrain", "deep_think", "local_think") if name in tool_names],
                "status": {
                    "cold_ok": brain_status.get("cold_ok"),
                    "vector_enabled": (brain_status.get("warm") or {}).get("vector_enabled"),
                    "vector_operational": (brain_status.get("warm") or {}).get("vector_operational"),
                    "retrieval_mode": (brain_status.get("warm") or {}).get("retrieval_mode"),
                    "vector_error": ((brain_status.get("warm") or {}).get("vector") or {}).get("last_runtime_error") or ((brain_status.get("warm") or {}).get("vector") or {}).get("error"),
                    "hot_kb": brain_status.get("hot_kb"),
                },
            },
            "body": {
                "limbs": [
                    name for name in (
                        "read_file", "write_file", "edit_file", "list_dir", "exec",
                        "task_inbox", "task_read", "task_write", "task_interrupt",
                        "screen", "spawn", "cron",
                    ) if name in tool_names
                ],
                "capability_map": limbs_detail,
            },
            "fallback_rules": {
                "principle": "一个工具失败 ≠ 任务失败，立即走备选链",
                "screen_失败": "exec命令行 → python脚本 → webbrowser模块 → 通知用户",
                "feishu_失败": "检查token → refresh → curl直调 → 本地保存+通知",
                "deep_think_失败": "降级到chat模型 → local_think → 分步推理",
                "exec_失败": "python等效实现 → 检查权限 → 替代命令",
                "spawn_失败": "当前上下文执行 → 拆分小步骤 → task_inbox",
            },
            "coordination": {
                "default_loop": "先判断，再执行，再把结果写回记忆",
                "long_task": "长任务优先走 spawn + TaskBridge",
                "recall": "做事前先看自知层和记忆层，明确自己会什么、不会什么、当前工具是否在线",
                "runtime_check": "网关没弹窗不等于没运行；先查计划任务、再查 nanobot gateway 进程、最后查 Telegram 409 冲突",
                "on_failure": "工具调用失败时，立即查询 fallback_rules 找备选链，不要直接报错给用户",
            },
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.write(cognition)
        return cognition

    def add_development_update(self, title: str, detail: str, category: str = "development") -> None:
        record = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "title": title,
            "detail": detail,
        }
        with open(SELF_UPDATES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def recent_updates(self, limit: int = 4) -> list[dict]:
        if not SELF_UPDATES_FILE.exists():
            return []
        rows = []
        for line in SELF_UPDATES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows[-limit:]

    def prompt_context(self, max_updates: int = 3) -> str:
        model = self.read()
        if not model:
            return ""
        updates = self.recent_updates(limit=max_updates)
        lines = [
            "## KyloSelf · 自知层",
            f"- 语言优先级: {model.get('identity', {}).get('language_priority', '中文优先')}",
            f"- 第一原则: {model.get('identity', {}).get('coordination_priority', '')}",
            f"- 大脑: {', '.join(model.get('brain', {}).get('analyze', [])) or '未识别'}",
            f"- 四肢: {', '.join(model.get('body', {}).get('limbs', [])) or '未识别'}",
            f"- 协同闭环: {model.get('coordination', {}).get('default_loop', '')}",
            f"- 运行诊断: {model.get('coordination', {}).get('runtime_check', '')}",
            f"- 失败策略: {model.get('coordination', {}).get('on_failure', '工具失败时查备选链')}",
        ]
        status = model.get("brain", {}).get("status", {})
        if status:
            lines.append(
                f"- 当前状态: cold_ok={status.get('cold_ok')} vector_enabled={status.get('vector_enabled')} "
                f"vector_operational={status.get('vector_operational')} retrieval_mode={status.get('retrieval_mode')}"
            )
            if status.get("vector_error"):
                lines.append(f"- 向量降级原因: {status.get('vector_error')[:120]}")

        # 能力域概览 + 降级路径
        cap_map = model.get("body", {}).get("capability_map", [])
        if cap_map:
            lines.append("")
            lines.append("### 能力域与降级路径")
            for cap in cap_map:
                online = cap.get("online", [])
                offline = cap.get("offline", [])
                status_str = "✅全部在线" if not offline else f"⚠️ 离线: {', '.join(offline)}"
                lines.append(
                    f"- **{cap['domain']}**: {', '.join(online) if online else '无'} ({status_str})"
                    f"  → 降级: {cap.get('fallback', '无')}"
                )

        # 降级规则摘要
        fallback = model.get("fallback_rules", {})
        if fallback and fallback.get("principle"):
            lines.append("")
            lines.append(f"### 降级原则: {fallback['principle']}")
            for key, val in fallback.items():
                if key != "principle":
                    lines.append(f"- {key}: {val}")

        if updates:
            lines.append("")
            lines.append("最近开发更新：")
            for item in updates:
                lines.append(f"- {item.get('title')}: {item.get('detail')[:120]}")
        return "\n".join(lines)


_self_model_instance: SelfModel | None = None


def get_self_model() -> SelfModel:
    global _self_model_instance
    if _self_model_instance is None:
        _self_model_instance = SelfModel()
    return _self_model_instance