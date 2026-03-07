"""
Kylopro 晨报官 (Daily Herald) — 定时汇报技能
============================================
按计划时间向 Telegram 推送系统状态、日报、心跳等信息。
使用 APScheduler 调度，无需系统任务计划程序。

使用方式：
    python -m skills.cron_report.reporter
    或在代码中：
    reporter = CronReporter()
    reporter.add_daily_report(hour=9, minute=0)
    reporter.start()
"""

from __future__ import annotations

import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil 未安装，系统指标功能不可用: pip install psutil")

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler 未安装: pip install apscheduler")


# ===========================================================
# 系统指标采集（本地，零 Token）
# ===========================================================

def _collect_system_metrics() -> dict[str, Any]:
    """采集系统状态指标（完全本地，不消耗 Token）。"""
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil 未安装"}

    try:
        cpu    = psutil.cpu_percent(interval=1)
        mem    = psutil.virtual_memory()
        disk   = psutil.disk_usage("C:\\")
        boot   = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot

        return {
            "cpu_percent":    cpu,
            "mem_percent":    mem.percent,
            "mem_used_gb":    round(mem.used / 1024**3, 1),
            "mem_total_gb":   round(mem.total / 1024**3, 1),
            "disk_percent":   disk.percent,
            "disk_used_gb":   round(disk.used / 1024**3, 1),
            "disk_total_gb":  round(disk.total / 1024**3, 1),
            "uptime_hours":   round(uptime.total_seconds() / 3600, 1),
            "platform":       platform.system(),
        }
    except Exception as e:
        return {"error": str(e)}


def _check_ollama_status() -> str:
    """检测 Ollama 是否在运行（本地 HTTP，不消耗接口额度）。"""
    import urllib.request
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        resp = urllib.request.urlopen(f"{ollama_base}/api/tags", timeout=3)
        return "[OK] 在线" if resp.status == 200 else f"[?] HTTP {resp.status}"
    except Exception:
        return "[FAIL] 离线"


# ===========================================================
# 报告内容构建
# ===========================================================

def _build_morning_report() -> str:
    """构建晨报内容（系统心跳 + 状态摘要）。"""
    now     = datetime.now().strftime("%Y-%m-%d %H:%M")
    metrics = _collect_system_metrics()
    ollama  = _check_ollama_status()

    if "error" in metrics:
        sys_block = f"系统指标：{metrics['error']}"
    else:
        cpu_bar   = "█" * int(metrics["cpu_percent"] / 10) + "░" * (10 - int(metrics["cpu_percent"] / 10))
        mem_bar   = "█" * int(metrics["mem_percent"] / 10) + "░" * (10 - int(metrics["mem_percent"] / 10))
        sys_block = (
            f"CPU    [{cpu_bar}] {metrics['cpu_percent']}%\n"
            f"RAM    [{mem_bar}] {metrics['mem_percent']}% "
            f"({metrics['mem_used_gb']}/{metrics['mem_total_gb']} GB)\n"
            f"Disk C [{metrics['disk_percent']}%] "
            f"{metrics['disk_used_gb']}/{metrics['disk_total_gb']} GB\n"
            f"Uptime {metrics['uptime_hours']} h"
        )

    report = (
        f"<b>[晨报] {now}</b>\n\n"
        f"<b>系统状态</b>\n"
        f"<code>{sys_block}</code>\n\n"
        f"<b>服务状态</b>\n"
        f"  Ollama: {ollama}\n"
        f"  DeepSeek: 云端就绪\n\n"
        f"Kylopro 一切正常，待命中。"
    )
    return report


def _build_evening_report() -> str:
    """构建晚报内容。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f"<b>[晚报] {now}</b>\n\n"
        "今日系统运行正常。\n"
        "如有异常，哨兵眼会实时推送告警。\n\n"
        "明天见！"
    )


# ===========================================================
# 主调度器类
# ===========================================================

class CronReporter:
    """
    晨报官定时汇报调度器。

    支持：
    - 每日定时晨报（系统心跳 + Ollama 状态）
    - 每日定时晚报
    - 自定义定时任务（传入任意异步函数）
    - Ollama 心跳检测（每 N 分钟）
    """

    def __init__(self) -> None:
        if not APSCHEDULER_AVAILABLE:
            raise RuntimeError("请先安装 APScheduler: pip install apscheduler")

        from skills.telegram_notify.notify import TelegramNotifier
        self._notifier = TelegramNotifier()
        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    def add_daily_report(
        self,
        hour: int,
        minute: int = 0,
        report_type: str = "morning",  # "morning" | "evening"
    ) -> "CronReporter":
        """添加每日定时报告。"""
        if report_type == "morning":
            job_fn  = self._send_morning_report
            job_id  = f"morning_{hour:02d}{minute:02d}"
            job_name = f"晨报 {hour:02d}:{minute:02d}"
        else:
            job_fn  = self._send_evening_report
            job_id  = f"evening_{hour:02d}{minute:02d}"
            job_name = f"晚报 {hour:02d}:{minute:02d}"

        self._scheduler.add_job(
            job_fn,
            trigger="cron",
            hour=hour,
            minute=minute,
            id=job_id,
            name=job_name,
            misfire_grace_time=300,
        )
        logger.info("[HERALD] 已注册: {} (每天 {:02d}:{:02d})", job_name, hour, minute)
        return self

    def add_ollama_heartbeat(self, interval_minutes: int = 60) -> "CronReporter":
        """
        添加 Ollama 心跳检测。
        每 interval_minutes 分钟检测一次，断线时 Telegram 告警。
        """
        self._scheduler.add_job(
            self._check_ollama_heartbeat,
            trigger="interval",
            minutes=interval_minutes,
            id="ollama_heartbeat",
            name=f"Ollama 心跳 (每{interval_minutes}分钟)",
        )
        logger.info("[HERALD] Ollama 心跳检测: 每 {} 分钟", interval_minutes)
        return self

    def add_custom(
        self,
        coro_fn: Any,
        hour: int | None = None,
        minute: int = 0,
        interval_minutes: int | None = None,
        job_id: str = "custom",
    ) -> "CronReporter":
        """添加自定义定时任务（传入异步函数）。"""
        if interval_minutes:
            self._scheduler.add_job(
                coro_fn,
                trigger="interval",
                minutes=interval_minutes,
                id=job_id,
            )
        elif hour is not None:
            self._scheduler.add_job(
                coro_fn,
                trigger="cron",
                hour=hour,
                minute=minute,
                id=job_id,
            )
        return self

    async def _send_morning_report(self) -> None:
        report = _build_morning_report()
        await self._notifier.send(report)
        logger.info("[HERALD] 晨报已发送")

    async def _send_evening_report(self) -> None:
        report = _build_evening_report()
        await self._notifier.send(report)
        logger.info("[HERALD] 晚报已发送")

    async def _check_ollama_heartbeat(self) -> None:
        status = _check_ollama_status()
        if "[FAIL]" in status:
            await self._notifier.send_alert(
                "Ollama 离线告警",
                f"Ollama 心跳检测失败：{status}\n请检查 ollama serve 是否在运行。"
            )
            logger.error("[HERALD] Ollama 离线: {}", status)
        else:
            logger.debug("[HERALD] Ollama 心跳: {}", status)

    def start(self) -> None:
        """启动调度器（阻塞，Ctrl+C 停止）。"""
        import asyncio

        async def _run() -> None:
            self._scheduler.start()
            logger.info("[HERALD] 晨报官已启动，共 {} 个任务", len(self._scheduler.get_jobs()))

            # 打印下次执行时间
            for job in self._scheduler.get_jobs():
                logger.info("  - {}: 下次执行 {}", job.name, job.next_run_time)

            # 发一条启动通知
            job_list = "\n".join(
                f"  - {job.name}" for job in self._scheduler.get_jobs()
            )
            await self._notifier.send(
                f"[HERALD] 晨报官已启动\n\n已注册任务：\n{job_list}"
            )

            try:
                while True:
                    await asyncio.sleep(60)
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                self._scheduler.shutdown()
                logger.info("[HERALD] 晨报官已停止")

        asyncio.run(_run())


# ===========================================================
# CLI 入口（默认配置：09:00 晨报 + 18:00 晚报 + 60分钟心跳）
# ===========================================================

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    load_dotenv(Path(__file__).parent.parent.parent / ".env")

    reporter = CronReporter()
    reporter.add_daily_report(hour=9, minute=0, report_type="morning")
    reporter.add_daily_report(hour=18, minute=0, report_type="evening")
    reporter.add_ollama_heartbeat(interval_minutes=60)
    reporter.start()
