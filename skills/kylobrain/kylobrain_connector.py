"""
KyloBrain · kylobrain_connector.py
=====================================
总装配：把所有模块连接成统一的 nanobot 扩展层

使用方式（在 decision_pool_system.py 顶部）：
  from kylobrain_connector import KyloConnector
  kc = KyloConnector()

连接点：
  · decision_pool_system.py   → BrainHooks（任务前后自动记录）
  · skill_evolution/verifier  → 验证成功 → 成就记录
  · nanobot core/engine.py    → world_model 持续更新
  · Cron 定时任务             → 每日巩固 + 每周周报

模块依赖图：
  cloud_brain.py         → MetaCogEngine（三层记忆）
  metacog_algorithms.py  → MetaCogAlgorithms（置信/布隆/图/研究）
  ide_bridge_enhanced.py → IDEOrchestrator（动手能力）
  kylobrain_connector.py → KyloConnector（总入口）
"""

from __future__ import annotations

import functools
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

# 模块导入（同目录）
import sys
_here = Path(__file__).parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

try:
    from cloud_brain import (
        MetaCogEngine, KyloBrainSkill,
        HotMemory, WarmMemory, ColdMemory, AwakeningProtocol,
    )
    _brain_ok = True
except ImportError as e:
    print(f"[KyloConnector] cloud_brain 导入失败: {e}")
    _brain_ok = False

try:
    from metacog_algorithms import MetaCogAlgorithms
    _algo_ok = True
except ImportError as e:
    print(f"[KyloConnector] metacog_algorithms 导入失败: {e}")
    _algo_ok = False

try:
    from ide_bridge_enhanced import IDEOrchestrator, IDESkill, VSCodeBridge
    _ide_ok = True
except ImportError as e:
    print(f"[KyloConnector] ide_bridge_enhanced 导入失败: {e}")
    _ide_ok = False

try:
    from credential_vault import CredentialVault, get_vault
    _vault_ok = True
except ImportError as e:
    print(f"[KyloConnector] credential_vault 导入失败: {e}")
    _vault_ok = False

try:
    from self_model import SelfModel, get_self_model
    _self_model_ok = True
except ImportError as e:
    print(f"[KyloConnector] self_model 导入失败: {e}")
    _self_model_ok = False


def _resolve_base_dir() -> Path:
    env_dir = os.environ.get("KYLOPRO_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    # skills/kylobrain/kylobrain_connector.py -> Kylopro-Nexus/
    repo_guess = Path(__file__).resolve().parents[2]
    cwd = Path.cwd().resolve()
    home_guess = Path.home() / "Kylopro-Nexus"
    for candidate in (repo_guess, cwd, home_guess):
        if (candidate / "brain").exists() and (candidate / "skills").exists():
            return candidate
    return repo_guess


BASE_DIR  = _resolve_base_dir()
BRAIN_DIR = BASE_DIR / "brain"

# 全局单例
_connector_instance: Optional["KyloConnector"] = None


def get_connector() -> Optional["KyloConnector"]:
    global _connector_instance
    if _connector_instance is None and (_brain_ok or _algo_ok or _ide_ok):
        _connector_instance = KyloConnector()
    return _connector_instance


# ══════════════════════════════════════════════
# 总连接器
# ══════════════════════════════════════════════

class KyloConnector:
    """
    所有模块的统一门面。
    外部代码只需要 import 这一个类。
    """

    def __init__(self, llm_caller: Optional[Callable] = None) -> None:
        self.llm_caller = llm_caller
        self._tasks: dict[str, dict] = {}  # task_id → {start, task, ...}

        # 按需初始化各模块
        self.brain = MetaCogEngine() if _brain_ok else None
        self.algos = MetaCogAlgorithms(llm_caller) if _algo_ok else None
        self.ide = IDEOrchestrator(
            brain_warm=self.brain.warm if self.brain else None,
            brain_cold=self.brain.cold if self.brain else None,
        ) if _ide_ok else None
        self.vault = get_vault() if _vault_ok else None
        self.self_model = get_self_model() if _self_model_ok else None

        vector_ok = False
        try:
            vector_ok = bool(self.brain and self.brain.warm and self.brain.warm.vector and self.brain.warm.vector.available())
        except Exception:
            vector_ok = False

        if self.self_model and self.brain:
            self.self_model.refresh(brain_status=self.brain.status())

        print(f"[KyloConnector] 初始化: brain={_brain_ok} algo={_algo_ok} ide={_ide_ok} vault={_vault_ok} vector={vector_ok}")

    def refresh_self_model(self, tool_names: list[str] | None = None, workspace: str = "") -> dict:
        if not self.self_model:
            return {}
        return self.self_model.refresh(
            brain_status=self.brain.status() if self.brain else {},
            tool_names=tool_names or [],
            workspace=workspace,
        )

    def record_dev_update(self, title: str, detail: str, category: str = "development") -> None:
        if self.self_model:
            self.self_model.add_development_update(title=title, detail=detail, category=category)

    # ══════════════════════════════════════════
    # 任务生命周期钩子
    # ══════════════════════════════════════════

    def on_task_start(self, task_id: str, task: str,
                      confidence: float = 0.7) -> dict:
        """
        任务开始时调用。
        返回一个"直觉包"，可以直接注入进 system prompt。
        """
        self._tasks[task_id] = {"start": time.time(), "task": task}
        hints = {}

        if self.brain:
            intuition = self.brain.pre_task_intuition(task)
            hints["brain_intuition"] = intuition

        if self.algos:
            algo_check = self.algos.pre_task_check(task, confidence)
            hints["algo_check"] = algo_check
            if algo_check.get("bloom_warning"):
                print(f"[⚠️ 布隆警告] 此类任务历史上失败过，置信度已调整为 {algo_check['adjusted_confidence']}")

        # 构建可直接注入 prompt 的文本
        prompt_hints = self._build_prompt_hints(hints)
        hints["prompt_hint_text"] = prompt_hints

        return hints

    def on_task_complete(
        self, task_id: str, outcome: str, success: bool,
        errors: list[str] = None, steps: int = 1,
        task_sequence: list[str] = None,
    ) -> dict:
        """任务完成时调用，自动更新所有算法和记忆"""
        task_info = self._tasks.pop(task_id, {})
        duration  = time.time() - task_info.get("start", time.time())
        task      = task_info.get("task", "unknown")
        errors    = errors or []

        result = {}

        if self.brain:
            score_r = self.brain.post_task_score(
                task=task, outcome=outcome,
                steps_taken=steps, duration_sec=duration,
                success=success, errors=errors,
            )
            result["score"] = score_r

        if self.algos:
            raw_conf = 0.8 if success else 0.3
            self.algos.post_task_update(
                task=task, success=success,
                predicted_conf=raw_conf,
                sequence=task_sequence,
            )

        return result

    def _build_prompt_hints(self, hints: dict) -> str:
        """把直觉包转换为可注入 prompt 的自然语言"""
        parts = []
        bi = hints.get("brain_intuition", {})
        if bi.get("similar_failure"):
            f = bi["similar_failure"]
            parts.append(f"⚠️ 历史警告：类似任务曾失败（{f.get('error','')[:60]}）")
            if f.get("recovery"):
                parts.append(f"   当时的修复：{f['recovery'][:80]}")
        if bi.get("best_pattern"):
            p = bi["best_pattern"]
            parts.append(f"💡 经验建议：{p['tip']}")
        if bi.get("hot_hint"):
            parts.append(f"📝 相关记忆：{'；'.join(bi['hot_hint'])}")
        ac = hints.get("algo_check", {})
        if ac.get("bloom_warning"):
            adj = ac.get("adjusted_confidence", 0.5)
            parts.append(f"🔬 置信校准：当前任务置信度已调整为 {adj:.0%}")
        if ac.get("workflow_hint"):
            wf = [w["next_task"] for w in ac["workflow_hint"][:2]]
            parts.append(f"🗺️ 工作流建议：下一步可能是 {' / '.join(wf)}")
        return "\n".join(parts) if parts else ""

    # ══════════════════════════════════════════
    # 成就 & 技能验证
    # ══════════════════════════════════════════

    def on_achievement(
        self, title: str, description: str, impact: str = "medium"
    ) -> None:
        """记录成就到云端"""
        if self.brain:
            self.brain.cold.record_achievement(title, description, impact)
            print(f"[🏆 成就] {title}")

    def on_skill_verified(self, skill_name: str, test_result: dict) -> None:
        """skill_evolution/verifier.py 验证通过后调用"""
        passed = test_result.get("passed", False)
        rate   = test_result.get("pass_rate", 1.0)
        count  = test_result.get("test_count", 1)

        if passed and self.brain:
            self.brain.warm.upsert_pattern(skill_name, "verified_skill", True)
            self.on_achievement(
                title=f"技能验证通过：{skill_name}",
                description=f"测试通过率 {rate:.0%}，共 {count} 个测试",
                impact="medium",
            )
        if self.algos and passed:
            self.algos.graph.record_sequence([skill_name, "verified"])

    # ══════════════════════════════════════════
    # IDE 动手操作
    # ══════════════════════════════════════════

    def execute_actions(
        self, task: str, actions: list[dict],
        auto_commit: bool = False,
    ) -> dict:
        """通过 IDE 编排器执行一组动作"""
        if not self.ide:
            return {"error": "IDE bridge not available"}
        result = self.ide.execute(task, actions, auto_commit)
        # 记录到成就（如果成功且是重要任务）
        if result.get("success") and len(actions) >= 3:
            self.on_achievement(
                title=f"完成多步任务：{task[:40]}",
                description=f"{len(actions)}个动作，耗时{result['duration']:.1f}s",
                impact="low",
            )
        return result

    # ══════════════════════════════════════════
    # 定时任务（Cron）
    # ══════════════════════════════════════════

    def daily_consolidation(self) -> dict:
        """每日凌晨执行：记忆巩固 + 算法检查 + 云端同步"""
        result = {}
        if self.brain:
            result["memory"] = self.brain.consolidate(self.llm_caller)

        if self.algos and self.brain:
            gaps = self.algos.researcher.detect_capability_gaps(self.brain.warm)
            result["capability_gaps"] = gaps

        print(f"[🧠 日常巩固] {result.get('memory', {}).get('summary', '完成')}")
        return result

    def weekly_digest_push(self) -> dict:
        """每周末执行：生成周报推送到 GitHub"""
        if not self.brain:
            return {"error": "brain not available"}
        digest = self.brain.weekly_digest()
        print(f"[📊 周报推送] 第{digest['week']}周，成功率{digest['stats']['rate']:.0%}")
        return digest

    def research_cycle(self) -> list[dict]:
        """每2周执行：算法自研周期"""
        if not self.algos or not self.brain:
            return [{"error": "algos or brain not available"}]
        return self.algos.researcher.full_research_cycle(self.brain.warm)

    # ══════════════════════════════════════════
    # 觉醒 & 迁移
    # ══════════════════════════════════════════

    def health_check(self) -> dict:
        if self.brain:
            return self.brain.awakening.check_health()
        return {"error": "brain not available"}

    def emergency_recover(self) -> dict:
        if self.brain:
            return self.brain.awakening.diagnose_and_recover()
        return {"error": "brain not available"}

    def migration_checklist(self) -> dict:
        if self.brain:
            return self.brain.awakening.migration_checklist()
        return {"error": "brain not available"}

    def get_soul_patches(self) -> dict:
        """获取需要追加到 SOUL.md 的所有补丁"""
        if self.algos:
            return self.algos.apply_soul_patches()
        return {}

    # ══════════════════════════════════════════
    # 偏好与失败模式（交互优化）
    # ══════════════════════════════════════════

    def record_preference(self, key: str, value: str, source: str = "clarification") -> None:
        if not self.brain:
            return
        self.brain.warm.append("preference", {
            "key": key,
            "value": value,
            "source": source,
            "ts": time.time(),
        })

    def recall_preference(self, key: str, limit: int = 3) -> list[dict]:
        if not self.brain:
            return []
        rows = self.brain.warm.read_all("preference")
        matched = [r for r in rows if r.get("key") == key]
        matched.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return matched[:limit]

    def record_failure(self, error_type: str, task: str, fix: str, success: bool) -> None:
        if not self.brain:
            return
        if not success:
            # Keep the canonical failures collection updated for pre_task_intuition.
            self.brain.warm.record_failure(task=task, error=error_type, recovery=fix)
        self.brain.warm.append("failure_patterns", {
            "error_type": error_type,
            "task": task,
            "fix": fix,
            "success": success,
            "ts": time.time(),
        })

    def recall_failure(self, error_type: str, limit: int = 5) -> list[dict]:
        if not self.brain:
            return []
        rows = self.brain.warm.read_all("failure_patterns")
        matched = [r for r in rows if r.get("error_type") == error_type]

        canonical = self.brain.warm.read_all("failures")
        for r in canonical:
            if error_type in str(r.get("error", "")):
                matched.append({
                    "error_type": error_type,
                    "task": r.get("task", ""),
                    "fix": r.get("recovery", ""),
                    "success": False,
                    "ts": r.get("_ts", 0),
                })

        matched.sort(key=lambda r: r.get("ts", 0), reverse=True)
        return matched[:limit]

    # ══════════════════════════════════════════
    # 状态报告
    # ══════════════════════════════════════════

    def full_status(self) -> dict:
        status: dict = {
            "modules": {
                "brain": _brain_ok,
                "algos": _algo_ok,
                "ide":   _ide_ok,
            }
        }
        if self.brain:
            status["brain"] = self.brain.status()
        if self.algos:
            status["algos"] = self.algos.full_status()
        if self.ide:
            status["ide"] = self.ide.full_status()
        if self.self_model:
            status["self_model"] = self.self_model.read()
        return status

    def inject_context(self, max_chars: int = 600) -> str:
        """
        获取大脑上下文字符串，可直接注入 system prompt。
        控制字符数避免撑爆 context window。
        """
        if not self.brain:
            return ""
        hot = self.brain.hot.read()
        return hot[-max_chars:] if len(hot) > max_chars else hot


# ══════════════════════════════════════════════
# 装饰器：自动追踪任务（最轻量的接入方式）
# ══════════════════════════════════════════════

def track_task(task_name_arg: str = "task", confidence: float = 0.7):
    """
    装饰器：自动在函数执行前后触发大脑记录。

    用法：
      @track_task(task_name_arg="task_description")
      def execute_task(self, task_description, ...):
          ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            conn = get_connector()
            task_str = kwargs.get(task_name_arg, "")
            if not task_str and args:
                task_str = str(args[1]) if len(args) > 1 else "unknown"

            task_id = f"{func.__name__}_{int(time.time()*1000)}"
            if conn:
                hints = conn.on_task_start(task_id, str(task_str), confidence)
                if hints.get("prompt_hint_text"):
                    print(f"[🧠 Brain Hint]\n{hints['prompt_hint_text']}")

            start   = time.time()
            success = True
            errors  = []
            result  = None

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                success = False
                errors.append(str(e))
                raise
            finally:
                if conn:
                    conn.on_task_complete(
                        task_id=task_id,
                        outcome=str(result)[:200] if result else "completed",
                        success=success,
                        errors=errors,
                        steps=1,
                    )

            return result
        return wrapper
    return decorator


# ══════════════════════════════════════════════
# nanobot tools.py 注册代码（可直接粘贴）
# ══════════════════════════════════════════════

TOOLS_REGISTRATION = """
# ── 在 core/tools.py 中添加 ──

from skills.kylobrain.kylobrain_connector import KyloConnector as _KC
_kc = _KC()

KYLOBRAIN_TOOLS = [
    {
        "name": "kylobrain_brain",
        "description": "Kylopro大脑：记忆查询、经验积累、任务评分、觉醒协议",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": ["pre_task","post_task","remember","recall",
                                    "consolidate","weekly","status","achieve",
                                    "health_check","recover","migrate","world_update"]},
                "params": {"type": "object"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "kylobrain_ide",
        "description": "IDE动手能力：VS Code文件读写、运行代码、测试、git操作",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": ["run","write","read","execute","write_test_fix",
                                    "status","git_status","run_tests","ag_status"]},
                "params": {"type": "object"}
            },
            "required": ["action"]
        }
    }
]

def handle_kylobrain(action: str, params: dict) -> dict:
    return _kc.brain.handle(action, params) if hasattr(_kc, 'brain') else {}

def handle_ide(action: str, params: dict) -> dict:
    if not _kc.ide: return {"error": "IDE not available"}
    from skills.kylobrain.ide_bridge_enhanced import IDESkill
    skill = IDESkill(_kc.brain.warm if _kc.brain else None,
                     _kc.brain.cold if _kc.brain else None)
    return skill.handle(action, params)
"""

# ══════════════════════════════════════════════
# Cron 配置片段
# ══════════════════════════════════════════════

CRON_CONFIG = {
    "tasks": [
        {
            "id": "brain_daily",
            "schedule": "0 3 * * *",
            "description": "每日凌晨3点：记忆巩固 + 能力缺口检测 + 云端同步",
            "action": "kylobrain_brain",
            "params": {"action": "consolidate"}
        },
        {
            "id": "brain_weekly",
            "schedule": "0 20 * * 0",
            "description": "每周日晚8点：周报生成 + GitHub推送",
            "action": "kylobrain_brain",
            "params": {"action": "weekly"}
        },
        {
            "id": "brain_health",
            "schedule": "0 */6 * * *",
            "description": "每6小时：三层记忆健康检查",
            "action": "kylobrain_brain",
            "params": {"action": "health_check"}
        }
    ]
}


# ══════════════════════════════════════════════
# CLI 总测试
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("🔗 KyloConnector — 总装配测试")
    print("=" * 52)

    kc = KyloConnector()
    print(f"已加载模块: brain={_brain_ok} algo={_algo_ok} ide={_ide_ok}")

    print("\n[1] 完整状态报告...")
    status = kc.full_status()
    mods = status.get("modules", {})
    for k, v in mods.items():
        print(f"    {k}: {'✅' if v else '❌'}")

    print("\n[2] 模拟任务生命周期...")
    task_id = "test_001"
    hints = kc.on_task_start(task_id, "在VS Code里调试Python环境问题", confidence=0.75)
    if hints.get("prompt_hint_text"):
        print(f"    提示:\n    {hints['prompt_hint_text']}")
    else:
        print("    （首次运行，暂无历史经验）")

    time.sleep(0.1)
    result = kc.on_task_complete(
        task_id=task_id, outcome="找到并修复venv路径问题",
        success=True, steps=4,
        task_sequence=["ide_ops", "debug", "testing"],
    )
    if result.get("score"):
        print(f"    评分: {result['score']['score']}/100")

    print("\n[3] 记录成就...")
    kc.on_achievement(
        "KyloBrain v2.0 总装配完成",
        "所有模块（brain/algo/ide）集成测试通过",
        impact="high"
    )

    print("\n[4] 获取 SOUL.md 补丁...")
    patches = kc.get_soul_patches()
    if patches.get("react_patch"):
        print(f"    ReAct 补丁已生成 ({len(patches['react_patch'])} 字符)")
        # 写入补丁文件供参考
        patch_path = BRAIN_DIR / "soul_patches.md"
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(
            "# SOUL.md 补丁\n\n" +
            patches.get("react_patch", "") + "\n\n---\n\n" +
            "## responder.py 建议\n\n```python\n" +
            patches.get("responder_hint", "") + "\n```",
            encoding="utf-8"
        )
        print(f"    已保存至: {patch_path}")

    print("\n[5] Cron 配置...")
    print(f"    已定义 {len(CRON_CONFIG['tasks'])} 个定时任务")
    for t in CRON_CONFIG["tasks"]:
        print(f"    · {t['id']}: {t['description']}")

    print(f"\n✅ KyloConnector 总装配测试完成")
    print(f"   模块目录: {_here}")
