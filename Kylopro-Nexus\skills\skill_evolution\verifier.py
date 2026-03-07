"""
Kylopro 技能自检器 (Skill Verifier)
====================================
开机/按需验证所有已装技能是否可正常导入和基础运行。
结果报告推 Telegram（可选），生成 JSON 状态文件。

原则: 自检本身走 Ollama（routine 任务），不消耗 DeepSeek 额度。
"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

# skills/ 目录
SKILLS_ROOT = Path(__file__).parent.parent


# ===========================================================
# 每个 Skill 的自检配置（告诉 verifier 怎么测它）
# ===========================================================
SKILL_CHECKS: dict[str, dict[str, Any]] = {
    "telegram_notify": {
        "module":  "skills.telegram_notify.notify",
        "class":   "TelegramNotifier",
        "check":   lambda obj: hasattr(obj, "send") and hasattr(obj, "_configured"),
        "desc":    "Telegram 推送",
    },
    "file_monitor": {
        "module":  "skills.file_monitor.monitor",
        "class":   "FileMonitor",
        "check":   lambda obj: hasattr(obj, "start"),
        "desc":    "哨兵眼文件监控",
        "skip_init": True,   # FileMonitor 需参数，只测导入
    },
    "cron_report": {
        "module":  "skills.cron_report.reporter",
        "class":   "CronReporter",
        "check":   lambda obj: True,
        "desc":    "晨报官定时汇报",
    },
    "web_pilot": {
        "module":  "skills.web_pilot.pilot",
        "class":   "WebPilot",
        "check":   lambda obj: hasattr(obj, "navigate"),
        "desc":    "网页触角 Playwright",
        "skip_init": True,
    },
    "vision_rpa": {
        "module":  "skills.vision_rpa.vision",
        "class":   "VisionRPA",
        "check":   lambda obj: hasattr(obj, "click"),
        "desc":    "全境飞行员 RPA",
    },
    "system_manager": {
        "module":  "skills.system_manager.manager",
        "class":   "SystemManager",
        "check":   lambda obj: hasattr(obj, "list_installed"),
        "desc":    "数字管家系统管理",
    },
    "ide_bridge": {
        "module":  "skills.ide_bridge.bridge",
        "class":   "IDEBridge",
        "check":   lambda obj: hasattr(obj, "read_file"),
        "desc":    "代码神经元 IDE 桥接",
        "skip_init": True,
    },
}


# ===========================================================
# 单项技能验证
# ===========================================================

async def _verify_skill(name: str, config: dict[str, Any]) -> dict[str, Any]:
    """验证单个技能，返回结果字典。"""
    result: dict[str, Any] = {
        "name":    name,
        "desc":    config.get("desc", name),
        "status":  "UNKNOWN",
        "detail":  "",
        "time_ms": 0,
    }

    t0 = asyncio.get_event_loop().time()
    try:
        # 层 1：导入模块
        mod = importlib.import_module(config["module"])
        cls = getattr(mod, config["class"])

        # 层 2：实例化（若不跳过）
        if not config.get("skip_init", False):
            if name == "ide_bridge":
                # IDEBridge 需要 workspace 参数
                obj = cls(str(SKILLS_ROOT.parent))
            else:
                obj = cls()

            # 层 3：运行用户定义的 check 函数
            ok = config["check"](obj)
            result["status"] = "OK" if ok else "WARN"
        else:
            # 只检查导入 + 类是否存在
            result["status"] = "OK"

        result["detail"] = "导入 + 实例化成功"

    except ImportError as e:
        result["status"] = "MISSING_DEP"
        result["detail"] = f"依赖缺失: {e}"
    except Exception as e:
        result["status"] = "FAIL"
        result["detail"] = str(e)[:120]
        logger.debug("Skill {} 自检异常: {}", name, traceback.format_exc()[:300])
    finally:
        result["time_ms"] = round((asyncio.get_event_loop().time() - t0) * 1000)

    return result


# ===========================================================
# 主类
# ===========================================================

class SkillVerifier:
    """
    技能自检器。
    并发验证所有已注册技能，汇总报告。
    """

    def __init__(self, skills_path: str | Path | None = None) -> None:
        self.skills_path = Path(skills_path or SKILLS_ROOT)
        self._report_path = self.skills_path.parent / "data" / "skill_status.json"

    async def run_all(
        self,
        notify_telegram: bool = True,
    ) -> dict[str, Any]:
        """
        验证所有注册技能，返回完整报告。
        结果同时保存到 data/skill_status.json 并可选推 Telegram。
        """
        logger.info("[VERIFIER] 开始技能全量自检，共 {} 项", len(SKILL_CHECKS))

        # 并发验证（节省时间）
        tasks = [_verify_skill(name, cfg) for name, cfg in SKILL_CHECKS.items()]
        results = await asyncio.gather(*tasks)

        ok_count   = sum(1 for r in results if r["status"] == "OK")
        fail_count = sum(1 for r in results if r["status"] in ("FAIL", "MISSING_DEP"))
        warn_count = sum(1 for r in results if r["status"] == "WARN")

        report = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total":   len(results),
                "ok":      ok_count,
                "fail":    fail_count,
                "warn":    warn_count,
            },
            "skills": {r["name"]: r for r in results},
        }

        # 保存 JSON 状态文件
        self._report_path.parent.mkdir(parents=True, exist_ok=True)
        self._report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("[VERIFIER] 自检完成: {}/{} OK", ok_count, len(results))

        # 推 Telegram
        if notify_telegram:
            await self._push_report(report)

        return report

    async def run_one(self, skill_name: str) -> dict[str, Any]:
        """验证单个技能。"""
        if skill_name not in SKILL_CHECKS:
            return {"name": skill_name, "status": "NOT_REGISTERED", "detail": "未在 SKILL_CHECKS 中注册"}
        return await _verify_skill(skill_name, SKILL_CHECKS[skill_name])

    async def _push_report(self, report: dict[str, Any]) -> None:
        """把自检报告推 Telegram。"""
        try:
            from skills.telegram_notify.notify import TelegramNotifier
            notifier = TelegramNotifier()
            if not notifier._configured:
                return

            summary = report["summary"]
            icon    = "OK" if summary["fail"] == 0 else "FAIL"
            lines   = [f"[{icon}] Kylopro 技能自检报告\n"]

            for skill_result in report["skills"].values():
                s      = skill_result["status"]
                emoji  = {"OK": "[OK]", "FAIL": "[FAIL]", "WARN": "[??]",
                          "MISSING_DEP": "[DEP]"}.get(s, "[?]")
                lines.append(f"{emoji} {skill_result['desc']} ({skill_result['time_ms']}ms)")
                if s != "OK":
                    lines.append(f"   -> {skill_result['detail']}")

            lines.append(f"\n共 {summary['total']} 项: "
                         f"{summary['ok']} OK / {summary['fail']} FAIL / {summary['warn']} WARN")

            await notifier.send("\n".join(lines))
        except Exception as e:
            logger.warning("[VERIFIER] Telegram 推送失败: {}", e)


# ===========================================================
# CLI 入口
# ===========================================================

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    async def main() -> None:
        v = SkillVerifier()
        report = await v.run_all(notify_telegram=True)
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))

    asyncio.run(main())
