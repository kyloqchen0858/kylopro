"""
Kylopro 财务与配额追踪模块

功能：
  - Tavily API 配额追踪（免费层 1000 次/月，耗尽自动降级到 DuckDuckGo）
  - 模型 token 费用追踪（人民币，按周限额控制）
  - 每周预算管理（用户设置限额，Kylo 根据余量决策）

配置文件：data/financial_config.json（用户可编辑）
状态文件：data/cost_state.json（自动维护，勿手动编辑）
"""

from __future__ import annotations

import json
from datetime import datetime, date
from pathlib import Path
from typing import Any


# ── 定价表（人民币 / 1000 tokens）─────────────────────────────────
# DeepSeek API 实际价格（参考 2026-03 官网，含 USD→CNY 约 7.2 汇率）
# 如价格变动，在 financial_config.json 的 model_pricing 中覆盖
DEFAULT_MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek/deepseek-chat": {
        "input_per_1k": 0.002,   # ¥0.002 / 1K input tokens
        "output_per_1k": 0.008,  # ¥0.008 / 1K output tokens
    },
    "deepseek/deepseek-reasoner": {
        "input_per_1k": 0.004,   # ¥0.004 / 1K（含 CoT tokens）
        "output_per_1k": 0.016,  # ¥0.016 / 1K output tokens
    },
    "minimax/abab6.5s-chat": {
        "input_per_1k": 0.001,
        "output_per_1k": 0.001,
    },
    "default": {
        "input_per_1k": 0.005,
        "output_per_1k": 0.010,
    },
}

DEFAULT_FINANCIAL_CONFIG: dict[str, Any] = {
    "weekly_budget_rmb": 20.0,     # 每周预算（人民币），用户可修改
    "budget_warn_threshold": 0.2,  # 剩余 20% 时警告
    "budget_stop_threshold": 0.05, # 剩余 5% 时停止非关键 API 调用
    "apis": {
        "tavily": {
            "monthly_free_credits": 1000,
            "credit_cost_per_search": 1,   # 每次搜索消耗 1 credit
        }
    },
    "model_pricing": {},  # 覆盖 DEFAULT_MODEL_PRICING 中的价格，空则使用默认值
}


class CostTracker:
    """Kylopro 财务追踪器（单例模式，通过 get_tracker() 获取）。"""

    def __init__(self, workspace: Path):
        self._data_dir = workspace / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._config_file = self._data_dir / "financial_config.json"
        self._state_file = self._data_dir / "cost_state.json"
        self._config: dict[str, Any] = self._load_config()
        self._state: dict[str, Any] = self._load_or_init_state()

    # ── 配置 ────────────────────────────────────────────────────────

    def _load_config(self) -> dict[str, Any]:
        if self._config_file.exists():
            try:
                return json.loads(self._config_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        # 首次运行，写入默认配置
        self._config_file.write_text(
            json.dumps(DEFAULT_FINANCIAL_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return dict(DEFAULT_FINANCIAL_CONFIG)

    def get_weekly_budget(self) -> float:
        return float(self._config.get("weekly_budget_rmb", 20.0))

    def set_weekly_budget(self, rmb: float) -> None:
        self._config["weekly_budget_rmb"] = rmb
        self._config_file.write_text(
            json.dumps(self._config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── 状态初始化 ───────────────────────────────────────────────────

    def _load_or_init_state(self) -> dict[str, Any]:
        if self._state_file.exists():
            try:
                state = json.loads(self._state_file.read_text(encoding="utf-8"))
                self._maybe_reset(state)
                return state
            except Exception:
                pass
        return self._new_state()

    def _new_state(self) -> dict[str, Any]:
        now = datetime.now()
        state: dict[str, Any] = {
            "month": now.strftime("%Y-%m"),
            "week_start": self._week_start_str(),
            "week_cost_rmb": 0.0,
            "total_cost_rmb": 0.0,
            "apis": {
                "tavily": {
                    "month": now.strftime("%Y-%m"),
                    "used_credits": 0,
                    "monthly_free_credits": self._config.get("apis", {})
                        .get("tavily", {}).get("monthly_free_credits", 1000),
                }
            },
            "models": {},
            "search_fallback_count": {"tavily": 0, "ddg": 0},
        }
        self._save_state(state)
        return state

    def _week_start_str(self) -> str:
        today = date.today()
        monday = today - __import__("datetime").timedelta(days=today.weekday())
        return monday.isoformat()

    def _maybe_reset(self, state: dict[str, Any]) -> None:
        now = datetime.now()
        changed = False

        # 月重置：Tavily 免费额度
        if state.get("apis", {}).get("tavily", {}).get("month") != now.strftime("%Y-%m"):
            state["apis"]["tavily"]["used_credits"] = 0
            state["apis"]["tavily"]["month"] = now.strftime("%Y-%m")
            state["month"] = now.strftime("%Y-%m")
            changed = True

        # 周重置：token 费用
        if state.get("week_start") != self._week_start_str():
            state["week_cost_rmb"] = 0.0
            state["week_start"] = self._week_start_str()
            changed = True

        if changed:
            self._save_state(state)

    def _save_state(self, state: dict[str, Any] | None = None) -> None:
        s = state if state is not None else self._state
        self._state_file.write_text(
            json.dumps(s, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Tavily 配额 ──────────────────────────────────────────────────

    def tavily_remaining(self) -> int:
        self._maybe_reset(self._state)
        monthly_free = self._state["apis"]["tavily"]["monthly_free_credits"]
        used = self._state["apis"]["tavily"]["used_credits"]
        return max(0, monthly_free - used)

    def tavily_ok(self) -> bool:
        """返回 True 表示 Tavily 还有免费额度可用。"""
        return self.tavily_remaining() > 0

    def record_tavily_call(self, credits: int = 1) -> None:
        self._maybe_reset(self._state)
        self._state["apis"]["tavily"]["used_credits"] += credits
        self._state["search_fallback_count"]["tavily"] = (
            self._state["search_fallback_count"].get("tavily", 0) + 1
        )
        self._save_state()

    def record_ddg_call(self) -> None:
        self._state["search_fallback_count"]["ddg"] = (
            self._state["search_fallback_count"].get("ddg", 0) + 1
        )
        self._save_state()

    # ── 模型 Token 费用 ──────────────────────────────────────────────

    def _get_pricing(self, model: str) -> dict[str, float]:
        user_override = self._config.get("model_pricing", {})
        if model in user_override:
            return user_override[model]
        return DEFAULT_MODEL_PRICING.get(model, DEFAULT_MODEL_PRICING["default"])

    def calc_token_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = self._get_pricing(model)
        cost = (
            input_tokens / 1000 * pricing["input_per_1k"]
            + output_tokens / 1000 * pricing["output_per_1k"]
        )
        return round(cost, 6)

    def record_token_usage(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """记录一次模型调用的 token 消耗，返回本次费用（人民币）。"""
        self._maybe_reset(self._state)
        cost = self.calc_token_cost(model, input_tokens, output_tokens)

        if model not in self._state["models"]:
            self._state["models"][model] = {
                "input_tokens": 0,
                "output_tokens": 0,
                "calls": 0,
                "total_cost_rmb": 0.0,
            }
        m = self._state["models"][model]
        m["input_tokens"] += input_tokens
        m["output_tokens"] += output_tokens
        m["calls"] += 1
        m["total_cost_rmb"] = round(m["total_cost_rmb"] + cost, 6)

        self._state["week_cost_rmb"] = round(self._state["week_cost_rmb"] + cost, 6)
        self._state["total_cost_rmb"] = round(self._state["total_cost_rmb"] + cost, 6)
        self._save_state()
        return cost

    # ── 预算 ─────────────────────────────────────────────────────────

    def weekly_remaining(self) -> float:
        self._maybe_reset(self._state)
        return round(self.get_weekly_budget() - self._state["week_cost_rmb"], 4)

    def budget_level(self) -> str:
        """返回预算状态: 'ok' | 'warn' | 'stop'"""
        budget = self.get_weekly_budget()
        if budget <= 0:
            return "ok"  # 未设限
        remaining = self.weekly_remaining()
        ratio = remaining / budget
        stop_threshold = self._config.get("budget_stop_threshold", 0.05)
        warn_threshold = self._config.get("budget_warn_threshold", 0.20)
        if ratio <= stop_threshold:
            return "stop"
        if ratio <= warn_threshold:
            return "warn"
        return "ok"

    def budget_ok(self, estimated_cost_rmb: float = 0.01) -> bool:
        """预算是否允许此次操作（True = 可以继续）。"""
        return self.weekly_remaining() >= estimated_cost_rmb

    # ── 报告 ─────────────────────────────────────────────────────────

    def summary(self) -> str:
        self._maybe_reset(self._state)
        budget = self.get_weekly_budget()
        remaining = self.weekly_remaining()
        tavily_rem = self.tavily_remaining()
        level = self.budget_level()
        level_icon = {"ok": "🟢", "warn": "🟡", "stop": "🔴"}.get(level, "⚪")

        lines = [
            f"## 财务状态 {level_icon}",
            f"",
            f"### 本周预算（人民币）",
            f"  周限额: ¥{budget:.2f}",
            f"  已用:   ¥{self._state['week_cost_rmb']:.4f}",
            f"  余额:   ¥{remaining:.4f} ({remaining/budget*100:.1f}%)" if budget > 0 else f"  余额:   ¥{remaining:.4f}（未设限）",
            f"",
            f"### Tavily 配额（本月）",
            f"  免费额度: {self._state['apis']['tavily']['monthly_free_credits']} 次",
            f"  已用:     {self._state['apis']['tavily']['used_credits']} 次",
            f"  剩余:     {tavily_rem} 次",
            f"  搜索后端: {'Tavily ✅' if tavily_rem > 0 else 'DuckDuckGo（Tavily 已耗尽）'}",
            f"",
            f"### 模型费用（总计 ¥{self._state['total_cost_rmb']:.4f}）",
        ]
        for model, stat in self._state.get("models", {}).items():
            short = model.split("/")[-1]
            lines.append(
                f"  {short}: {stat['calls']}次 | in={stat['input_tokens']}tok"
                f" out={stat['output_tokens']}tok | ¥{stat['total_cost_rmb']:.4f}"
            )
        if not self._state.get("models"):
            lines.append("  （暂无记录）")

        lines += [
            f"",
            f"### 搜索调用次数",
            f"  Tavily: {self._state['search_fallback_count'].get('tavily', 0)} 次",
            f"  DuckDuckGo: {self._state['search_fallback_count'].get('ddg', 0)} 次",
        ]
        return "\n".join(lines)

    def get_state(self) -> dict[str, Any]:
        self._maybe_reset(self._state)
        return dict(self._state)


# ── 全局单例 ──────────────────────────────────────────────────────

_tracker_instance: CostTracker | None = None


def get_tracker(workspace: Path) -> CostTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = CostTracker(workspace)
    return _tracker_instance
