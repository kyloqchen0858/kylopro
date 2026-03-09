"""Shared task state bridge for main agent and subagents."""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TaskBridge:
    """Manage a shared task state file for progress tracking and interruption.

    The bridge is written by both the main agent and subagents, so writes must
    be atomic and tolerant of short-lived file locking on Windows.
    """

    def __init__(self, workspace: Path):
        self._tasks_dir = workspace / "tasks"
        self._state_path = self._tasks_dir / "active_task.json"
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self.ensure_state_file()

    @property
    def state_path(self) -> Path:
        return self._state_path

    def ensure_state_file(self) -> None:
        if self._state_path.exists():
            return
        self._write_state_with_retry(self.default_state())

    def default_state(self) -> dict[str, Any]:
        return {
            "task_id": None,
            "title": None,
            "status": "idle",
            "owner": "main",
            "progress": 0,
            "current_step": None,
            "summary": "No active task.",
            "detail": None,
            "interrupt_requested": False,
            "interrupt_reason": None,
            "max_iterations": 0,
            "max_runtime_seconds": 0,
            "clarification_pending": False,
            "clarification_question": None,
            "fix_history": [],
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            "history": [],
            "metadata": {},
        }

    def read_state(self) -> dict[str, Any]:
        self.ensure_state_file()
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = self.default_state()
            state["summary"] = "State file was invalid and has been reset."
            self._write_state_with_retry(state)
            return state

    def write_state(
        self,
        *,
        task_id: str | None = None,
        title: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        summary: str | None = None,
        detail: str | None = None,
        max_iterations: int | None = None,
        max_runtime_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
        append_history: str | None = None,
        clear_interrupt: bool = False,
        clarification_pending: bool | None = None,
        clarification_question: str | None = None,
        append_fix: dict[str, Any] | None = None,
        reset: bool = False,
    ) -> dict[str, Any]:
        state = self.default_state() if reset else self.read_state()

        updates = {
            "task_id": task_id,
            "title": title,
            "status": status,
            "owner": owner,
            "progress": progress,
            "current_step": current_step,
            "summary": summary,
            "detail": detail,
            "max_iterations": max_iterations,
            "max_runtime_seconds": max_runtime_seconds,
        }
        for key, value in updates.items():
            if value is not None:
                state[key] = value

        if metadata is not None:
            merged = dict(state.get("metadata") or {})
            merged.update(metadata)
            state["metadata"] = merged

        if clear_interrupt:
            state["interrupt_requested"] = False
            state["interrupt_reason"] = None

        if clarification_pending is not None:
            state["clarification_pending"] = clarification_pending
        if clarification_question is not None:
            state["clarification_question"] = clarification_question

        if append_fix:
            fix_history = list(state.get("fix_history") or [])
            fix_history.append(append_fix)
            state["fix_history"] = fix_history[-20:]

        if append_history:
            history = list(state.get("history") or [])
            history.append({"timestamp": _utc_now(), "message": append_history})
            state["history"] = history[-20:]

        state["updated_at"] = _utc_now()
        self._write_state_with_retry(state)
        return state

    def interrupt(self, reason: str | None = None) -> dict[str, Any]:
        state = self.read_state()
        state["interrupt_requested"] = True
        state["interrupt_reason"] = reason or "User requested stop."
        state["updated_at"] = _utc_now()
        history = list(state.get("history") or [])
        history.append({"timestamp": state["updated_at"], "message": f"Interrupt requested: {state['interrupt_reason']}"})
        state["history"] = history[-20:]
        self._write_state_with_retry(state)
        return state

    def check_interrupt(self) -> tuple[bool, str | None]:
        """Return whether an interrupt was requested and its reason."""
        state = self.read_state()
        return state.get("interrupt_requested", False), state.get("interrupt_reason")

    def should_stop(self) -> bool:
        """Convenience helper for long-running loops."""
        interrupted, _ = self.check_interrupt()
        return interrupted

    def format_state(self, state: dict[str, Any], mode: str = "summary") -> str:
        if mode == "json":
            return json.dumps(state, ensure_ascii=False, indent=2)

        history = state.get("history") or []
        tail = history[-3:]
        lines = [
            f"task_id: {state.get('task_id') or '-'}",
            f"title: {state.get('title') or '-'}",
            f"status: {state.get('status') or '-'}",
            f"owner: {state.get('owner') or '-'}",
            f"progress: {state.get('progress', 0)}%",
            f"current_step: {state.get('current_step') or '-'}",
            f"summary: {state.get('summary') or '-'}",
            f"detail: {state.get('detail') or '-'}",
            f"interrupt_requested: {state.get('interrupt_requested', False)}",
            f"interrupt_reason: {state.get('interrupt_reason') or '-'}",
            f"max_iterations: {state.get('max_iterations', 0)}",
            f"max_runtime_seconds: {state.get('max_runtime_seconds', 0)}",
            f"updated_at: {state.get('updated_at') or '-'}",
        ]
        if tail:
            lines.append("recent_history:")
            for item in tail:
                lines.append(f"- {item.get('timestamp', '-')}: {item.get('message', '')}")
        return "\n".join(lines)

    def _write_state_with_retry(self, state: dict[str, Any], max_retries: int = 3) -> None:
        """Retry atomic writes to survive short Windows file locking conflicts."""
        for attempt in range(max_retries):
            try:
                self._write_state_atomic(state)
                return
            except (PermissionError, OSError) as exc:
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Failed to write task state after {max_retries} attempts: {exc}"
                    ) from exc
                time.sleep((attempt + 1) * 0.1)

    def _write_state_atomic(self, state: dict[str, Any]) -> None:
        """Write via a unique temp file, then replace atomically."""
        temp_suffix = f".{uuid.uuid4().hex[:8]}.tmp"
        temp_path = self._state_path.with_suffix(temp_suffix)
        try:
            temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self._state_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
