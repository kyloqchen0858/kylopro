"""
Kylopro 任务收件箱 (Task Inbox)
================================
监控热目录 data/inbox/，接收 Markdown 需求文档，
自动解析 → 调度 → 执行 → 归档 → 推送结果。

核心流程：
  1. 发现新 .md/.txt 文件（watchdog 或轮询）
  2. 调用 parser 解析为结构化任务
  3. 调用 dispatcher 逐个执行子任务
  4. 完成后归档文件（done/ 或 failed/）
  5. 通过 Telegram 推送结果报告

使用方式：
    inbox = TaskInbox(workspace="c:/MyProject")
    await inbox.start()  # 启动热目录监控（阻塞）
    # 或
    await inbox.submit_file("requirements.md")  # 手动投递单个文件
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from core.responder import global_task_context
from .phased_notifier import PhasedNotifier, create_phased_notifier

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass


# 支持的需求文档扩展名
REQUIREMENT_EXTENSIONS = {".md", ".txt", ".markdown"}


class TaskRecord:
    """单个任务的状态记录。"""

    def __init__(self, file_path: Path, task_id: str = "") -> None:
        self.task_id = task_id or uuid.uuid4().hex[:8]
        self.file_path = file_path
        self.file_name = file_path.name
        self.status = "pending"   # pending → parsing → executing → done / failed
        self.created_at = datetime.now()
        self.completed_at: datetime | None = None
        self.parsed_data: dict[str, Any] = {}
        self.result: dict[str, Any] = {}
        self.error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id":      self.task_id,
            "file_name":    self.file_name,
            "status":       self.status,
            "created_at":   self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "title":        self.parsed_data.get("title", ""),
            "subtasks":     len(self.parsed_data.get("subtasks", [])),
            "success":      self.result.get("success", 0),
            "failed":       self.result.get("failed", 0),
            "error":        self.error,
        }

    def __repr__(self) -> str:
        return f"<Task {self.task_id}: {self.file_name} [{self.status}]>"


class TaskInbox:
    """
    任务收件箱。

    监控热目录，接收 Markdown 需求文档并自动执行。

    Args:
        workspace:   项目工作目录（子任务在此目录下执行）
        inbox_dir:   热目录路径（默认 data/inbox/）
        auto_execute: 是否自动执行解析后的任务（默认 True）
        notify:      是否通过 Telegram 推送进度（默认 True）
    """

    def __init__(
        self,
        workspace: str | Path = ".",
        inbox_dir: str | Path | None = None,
        auto_execute: bool = True,
        notify: bool = True,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.inbox_dir = Path(inbox_dir) if inbox_dir else (
            self.workspace / "data" / "inbox"
        )
        self.done_dir = self.inbox_dir / "done"
        self.failed_dir = self.inbox_dir / "failed"
        self.auto_execute = auto_execute
        self.notify = notify

        # 创建目录
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.done_dir.mkdir(parents=True, exist_ok=True)
        self.failed_dir.mkdir(parents=True, exist_ok=True)

        # 任务队列和历史
        self._queue: asyncio.Queue[Path] = asyncio.Queue()
        self._history: list[TaskRecord] = []
        self._running = False

        # 延迟导入
        self._parser = None
        self._dispatcher = None
        self._notifier = None

    def _get_parser(self):
        if self._parser is None:
            from skills.task_inbox.parser import RequirementParser
            self._parser = RequirementParser()
        return self._parser

    def _get_dispatcher(self):
        if self._dispatcher is None:
            from skills.task_inbox.dispatcher import TaskDispatcher
            self._dispatcher = TaskDispatcher(self.workspace)
        return self._dispatcher

    def _get_notifier(self):
        if self._notifier is None:
            try:
                from skills.telegram_notify.notify import TelegramNotifier
                self._notifier = TelegramNotifier()
            except Exception:
                self._notifier = None
        return self._notifier

    async def _notify(self, message: str) -> None:
        """通过 Telegram 推送消息（静默失败）。"""
        if not self.notify:
            return
        try:
            notifier = self._get_notifier()
            if notifier and hasattr(notifier, "_configured") and notifier._configured:
                await notifier.send(message)
        except Exception as e:
            logger.warning("[INBOX] Telegram 推送失败: {}", e)

    # -----------------------------------------------------------
    # 核心流程
    # -----------------------------------------------------------

    async def submit_file(self, file_path: str | Path) -> TaskRecord:
        """
        手动投递一个需求文件并处理。

        Args:
            file_path: 需求文件的路径（绝对路径或相对路径）

        Returns:
            TaskRecord 包含执行结果
        """
        path = Path(file_path)
        if not path.is_absolute():
            path = self.workspace / path
        if not path.exists():
            raise FileNotFoundError(f"需求文件不存在: {path}")

        logger.info("[INBOX] 手动投递: {}", path.name)
        return await self._process_file(path)

    async def _process_file(self, file_path: Path) -> TaskRecord:
        """处理单个需求文件的完整生命周期。"""
        record = TaskRecord(file_path)
        self._history.append(record)

        # 分阶段通知器
        phased_notifier = None

        try:
            # 1. 通知：新任务到达
            await self._notify(
                f"📥 <b>新任务到达</b>\n\n"
                f"文件: <b>{record.file_name}</b>\n"
                f"任务 ID: <code>{record.task_id}</code>"
            )

            # 2. 解析
            record.status = "parsing"
            logger.info("[INBOX] [{}] 解析中...", record.task_id)

            parser = self._get_parser()
            record.parsed_data = await parser.parse_file(file_path)

            title = record.parsed_data.get("title", "未命名")
            subtask_count = len(record.parsed_data.get("subtasks", []))

            # 创建分阶段通知器
            phased_notifier = create_phased_notifier(self, title)
            await phased_notifier.start()
            
            await self._notify(
                f"🧠 <b>需求解析完成</b>\n\n"
                f"任务: <b>{title}</b>\n"
                f"子任务数: {subtask_count}\n"
                f"ID: <code>{record.task_id}</code>"
            )

            if not self.auto_execute:
                record.status = "parsed"
                logger.info("[INBOX] [{}] 已解析，等待手动执行", record.task_id)
                return record

            # 3. 执行
            record.status = "executing"
            logger.info("[INBOX] [{}] 开始执行 {} 个子任务", record.task_id, subtask_count)

            dispatcher = self._get_dispatcher()
            
            # 初始化全局任务上下文，供 Responder 读取
            global_task_context.start(task_name=title)
            global_task_context.update_progress(f"准备执行 {subtask_count} 个子任务...")

            # 进入分析阶段
            if phased_notifier:
                await phased_notifier.enter_phase(PhasedNotifier.TaskPhase.ANALYZING)

            async def on_progress(st_id: int, status: str, message: str):
                prog_msg = f"子任务 #{st_id} [{status}] {message}"
                global_task_context.update_progress(prog_msg)
                
                # 使用分阶段通知器报告进度
                if phased_notifier:
                    # 更新子任务进度
                    completed = st_id  # 假设st_id是已完成的任务数
                    await phased_notifier.update_subtask_progress(
                        completed=completed,
                        total=subtask_count,
                        subtask_name=message[:50]  # 截取前50字符
                    )
                
                # 原始通知（保持兼容）
                await self._notify(f"⚙️ {prog_msg}")

            # 进入处理阶段
            if phased_notifier:
                await phased_notifier.enter_phase(PhasedNotifier.TaskPhase.PROCESSING)

            record.result = await dispatcher.execute_all(
                task_data=record.parsed_data,
                task_id=record.task_id,
                on_progress=on_progress,
                check_interrupt=global_task_context.check_interrupt
            )

            # 检查是否被中断
            if global_task_context.check_interrupt():
                record.status = "interrupted"
                record.error = "用户手动中断了任务"
                record.completed_at = datetime.now()
                self._archive_file(file_path, self.failed_dir)
                
                # 分阶段通知器报告中断
                if phased_notifier:
                    await phased_notifier.complete(success=False)
                
                await self._notify(f"🛑 <b>任务已被中断</b>\n\n文件: {record.file_name}")
                logger.warning("[INBOX] [{}] 任务被用户手动中断", record.task_id)
            else:
                # 进入收尾阶段
                if phased_notifier:
                    await phased_notifier.enter_phase(PhasedNotifier.TaskPhase.FINALIZING)
                
                # 4. 完成
                record.status = "done"
                record.completed_at = datetime.now()

                # 归档到 done/
                self._archive_file(file_path, self.done_dir)

                # 推送汇总报告
                report = dispatcher.format_report(record.result)
                await self._notify(report)
                
                # 分阶段通知器报告完成
                if phased_notifier:
                    success_count = record.result.get("success", 0)
                    failed_count = record.result.get("failed", 0)
                    result_summary = f"成功: {success_count}, 失败: {failed_count}"
                    await phased_notifier.complete(success=True, result=result_summary)

                logger.info("[INBOX] [{}] 任务完成 ✅", record.task_id)

        except Exception as e:
            record.status = "failed"
            record.error = str(e)
            record.completed_at = datetime.now()

            # 归档到 failed/
            self._archive_file(file_path, self.failed_dir)

            await self._notify(
                f"❌ <b>任务失败</b>\n\n"
                f"文件: {record.file_name}\n"
                f"ID: <code>{record.task_id}</code>\n"
                f"错误: {str(e)[:200]}"
            )

            logger.error("[INBOX] [{}] 任务失败: {}", record.task_id, e)
            
        finally:
            # 无论成功失败，重置共享状态
            global_task_context.stop()

        return record

    @staticmethod
    def _archive_file(src: Path, dest_dir: Path) -> None:
        """将文件移动到归档目录（同名文件追加时间戳）。"""
        dest = dest_dir / src.name
        if dest.exists():
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            dest = dest_dir / f"{src.stem}_{ts}{src.suffix}"
        try:
            shutil.move(str(src), str(dest))
            logger.info("[INBOX] 归档: {} → {}", src.name, dest.parent.name)
        except Exception as e:
            logger.warning("[INBOX] 归档失败: {}", e)

    # -----------------------------------------------------------
    # 热目录监控
    # -----------------------------------------------------------

    async def start(self) -> None:
        """
        启动热目录监控（阻塞，Ctrl+C 停止）。

        支持两种模式：
          1. watchdog 文件系统事件监控（推荐）
          2. 轮询模式（watchdog 不可用时降级）
        """
        self._running = True
        logger.info("[INBOX] 启动任务收件箱")
        logger.info("[INBOX] 热目录: {}", self.inbox_dir)
        logger.info("[INBOX] 工作区: {}", self.workspace)

        await self._notify(
            f"📬 <b>任务收件箱已启动</b>\n\n"
            f"热目录: <code>{self.inbox_dir}</code>\n"
            f"工作区: <code>{self.workspace}</code>\n\n"
            f"将 .md 文件放入热目录即可触发任务执行"
        )

        # 先处理 inbox 中已有的文件
        await self._scan_existing()

        # 启动监控
        try:
            from watchdog.events import FileSystemEventHandler, FileCreatedEvent
            from watchdog.observers import Observer

            await self._start_watchdog()
        except ImportError:
            logger.warning("[INBOX] watchdog 未安装，使用轮询模式")
            await self._start_polling()

    async def _scan_existing(self) -> None:
        """扫描 inbox 中已存在的需求文件。"""
        existing = [
            f for f in self.inbox_dir.iterdir()
            if f.is_file() and f.suffix.lower() in REQUIREMENT_EXTENSIONS
        ]
        if existing:
            logger.info("[INBOX] 发现 {} 个待处理文件", len(existing))
            for f in sorted(existing, key=lambda x: x.stat().st_mtime):
                await self._process_file(f)

    async def _start_watchdog(self) -> None:
        """使用 watchdog 监控目录变化。"""
        from watchdog.events import FileSystemEventHandler, FileCreatedEvent
        from watchdog.observers import Observer

        loop = asyncio.get_event_loop()

        class InboxHandler(FileSystemEventHandler):
            def __init__(self, queue: asyncio.Queue, event_loop):
                super().__init__()
                self._queue = queue
                self._loop = event_loop

            def on_created(self, event):
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if path.suffix.lower() in REQUIREMENT_EXTENSIONS:
                    self._loop.call_soon_threadsafe(
                        self._queue.put_nowait, path
                    )

        observer = Observer()
        observer.schedule(InboxHandler(self._queue, loop), str(self.inbox_dir), recursive=False)
        observer.start()
        logger.info("[INBOX] watchdog 监控已启动")

        try:
            while self._running:
                try:
                    file_path = await asyncio.wait_for(self._queue.get(), timeout=2.0)
                    # 等待文件写入完成（避免读取到半截文件）
                    await asyncio.sleep(1.0)
                    if file_path.exists():
                        await self._process_file(file_path)
                except asyncio.TimeoutError:
                    continue
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            observer.stop()
            observer.join()
            logger.info("[INBOX] watchdog 监控已停止")

    async def _start_polling(self, interval: float = 3.0) -> None:
        """轮询模式监控目录（watchdog 不可用时的降级方案）。"""
        logger.info("[INBOX] 轮询模式启动（间隔 {}s）", interval)
        known_files: set[str] = {
            str(f) for f in self.inbox_dir.iterdir() if f.is_file()
        }

        try:
            while self._running:
                await asyncio.sleep(interval)
                current_files = {
                    str(f) for f in self.inbox_dir.iterdir()
                    if f.is_file() and f.suffix.lower() in REQUIREMENT_EXTENSIONS
                }
                new_files = current_files - known_files
                for f_str in sorted(new_files):
                    f = Path(f_str)
                    # 等待文件写入完成
                    await asyncio.sleep(1.0)
                    if f.exists():
                        await self._process_file(f)
                known_files = {
                    str(f) for f in self.inbox_dir.iterdir() if f.is_file()
                }
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            logger.info("[INBOX] 轮询监控已停止")

    def stop(self) -> None:
        """停止监控。"""
        self._running = False
        logger.info("[INBOX] 收到停止信号")

    # -----------------------------------------------------------
    # 查询接口
    # -----------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """获取 inbox 状态概要。"""
        pending = [r for r in self._history if r.status in ("pending", "parsing", "executing")]
        done = [r for r in self._history if r.status == "done"]
        failed = [r for r in self._history if r.status == "failed"]

        return {
            "running":  self._running,
            "inbox_dir": str(self.inbox_dir),
            "pending":  len(pending),
            "done":     len(done),
            "failed":   len(failed),
            "total":    len(self._history),
        }

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """获取最近的任务历史。"""
        return [r.to_dict() for r in self._history[-limit:]]

    def format_status(self) -> str:
        """格式化状态输出（CLI 用）。"""
        s = self.get_status()
        lines = [
            "📬 任务收件箱状态",
            f"  运行中: {'✅ 是' if s['running'] else '❌ 否'}",
            f"  热目录: {s['inbox_dir']}",
            f"  待处理: {s['pending']}",
            f"  已完成: {s['done']}",
            f"  已失败: {s['failed']}",
            f"  总计:   {s['total']}",
        ]
        return "\n".join(lines)

    def format_history(self, limit: int = 5) -> str:
        """格式化历史输出（CLI 用）。"""
        history = self.get_history(limit)
        if not history:
            return "📋 暂无任务历史"
        lines = ["📋 最近任务:"]
        for h in history:
            icon = {"done": "✅", "failed": "❌", "executing": "⚙️", "parsing": "🧠"}.get(
                h["status"], "⏳"
            )
            lines.append(
                f"  {icon} [{h['task_id']}] {h['file_name']} — {h['title'] or '未命名'}"
            )
        return "\n".join(lines)


# ===========================================================
# CLI 入口
# ===========================================================

if __name__ == "__main__":
    import argparse

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    parser = argparse.ArgumentParser(description="Kylopro 任务收件箱")
    parser.add_argument("--workspace", default=".", help="项目工作目录")
    parser.add_argument("--inbox", default=None, help="热目录路径（默认 data/inbox/）")
    parser.add_argument("--submit", default="", help="手动投递需求文件")
    parser.add_argument("--no-execute", action="store_true", help="只解析不执行")
    args = parser.parse_args()

    inbox = TaskInbox(
        workspace=args.workspace,
        inbox_dir=args.inbox,
        auto_execute=not args.no_execute,
    )

    async def main() -> None:
        if args.submit:
            record = await inbox.submit_file(args.submit)
            print(f"\n任务结果: {record}")
            if record.result:
                for r in record.result.get("results", []):
                    icon = "✅" if r["status"] == "success" else "❌"
                    print(f"  {icon} #{r['id']} {r['action']}: {r['output'][:80]}")
        else:
            await inbox.start()

    asyncio.run(main())