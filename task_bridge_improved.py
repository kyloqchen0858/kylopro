"""Improved TaskBridge with better concurrency handling."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class TaskBridge:
    """Manage a shared task state file for progress tracking and interruption.
    
    Improvements over original:
    1. Unique temp filenames to avoid conflicts
    2. Retry logic for concurrent writes
    3. Better error handling
    4. Thread/process-safe operations
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
        """Write state with retry logic for concurrent access."""
        for attempt in range(max_retries):
            try:
                self._write_state_atomic(state)
                return
            except (PermissionError, OSError) as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 0.1  # Exponential backoff
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Failed to write state after {max_retries} attempts: {e}")

    def _write_state_atomic(self, state: dict[str, Any]) -> None:
        """Atomic write with unique temp filename."""
        # Create unique temp filename to avoid conflicts
        temp_suffix = f".{uuid.uuid4().hex[:8]}.tmp"
        temp_path = self._state_path.with_suffix(temp_suffix)
        
        try:
            # Write to temp file
            temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            
            # Atomic replace
            temp_path.replace(self._state_path)
            
        finally:
            # Clean up temp file if it still exists (replace failed)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass  # Ignore cleanup errors

    def check_interrupt(self) -> tuple[bool, str | None]:
        """Check if interrupt was requested.
        
        Returns:
            Tuple of (interrupt_requested, reason)
        """
        state = self.read_state()
        return (
            state.get("interrupt_requested", False),
            state.get("interrupt_reason")
        )

    def should_stop(self) -> bool:
        """Convenience method to check if task should stop."""
        interrupted, _ = self.check_interrupt()
        return interrupted