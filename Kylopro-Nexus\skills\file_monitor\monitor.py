"""
Kylopro 哨兵眼 (Sentinel Eye) — 文件监控技能
============================================
监控指定目录的文件变动，用 Ollama 本地生成摘要，
有变化时通过 Telegram 告警。

隐私优先：文件内容在本地 Ollama 处理，只把摘要发给 Telegram。
Token 省钱：不把原文件发给 DeepSeek，OCR/摘要全走本地。

使用方式：
    python -m skills.file_monitor.monitor --path "C:/Users/qianchen/Downloads"
    或在代码中：
    monitor = FileMonitor("C:/Users/qianchen/Downloads")
    await monitor.start()
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from loguru import logger

# 确保 Windows UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

# 延迟导入（watchdog 可能未安装）
try:
    from watchdog.events import FileSystemEvent, FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog 未安装，请运行: pip install watchdog>=4.0.0")


# ===========================================================
# 文件内容读取（带安全限制）
# ===========================================================

def _read_file_preview(path: Path, max_chars: int = 800) -> str:
    """
    安全读取文件前 max_chars 个字符。
    二进制文件返回描述性提示，不上传任何字节。
    """
    try:
        # 只读文本文件（后缀白名单）
        TEXT_EXTS = {
            ".txt", ".md", ".log", ".py", ".js", ".ts", ".json",
            ".yml", ".yaml", ".csv", ".ini", ".cfg", ".toml",
            ".html", ".css", ".xml", ".sh", ".bat",
        }
        if path.suffix.lower() not in TEXT_EXTS:
            return f"[二进制或非文本文件: {path.suffix}，跳过内容读取]"
        content = path.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n...[截断，原文件 {len(content)} 字符]"
        return content
    except PermissionError:
        return "[权限不足，无法读取]"
    except Exception as e:
        return f"[读取失败: {e}]"


# ===========================================================
# Ollama 本地摘要（完全本地，零 Token 消耗）
# ===========================================================

async def _ollama_summarize(content: str, filename: str) -> str:
    """
    用本地 Ollama 对文件内容生成摘要。
    完全本地运行，不消耗 DeepSeek 额度。
    """
    import os
    from openai import AsyncOpenAI

    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "deepseek-r1:latest")

    client = AsyncOpenAI(api_key="ollama", base_url=f"{ollama_base}/v1")

    prompt = (
        f"文件名：{filename}\n"
        f"内容预览：\n{content}\n\n"
        f"请用一两句话概括这个文件的主要内容是什么。直接说结论，不要废话。"
    )

    try:
        resp = await client.chat.completions.create(
            model=ollama_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.1,
        )
        return resp.choices[0].message.content or "[摘要为空]"
    except Exception as e:
        logger.warning("Ollama 摘要失败: {}", e)
        return f"[Ollama 摘要失败: {e}]"


# ===========================================================
# 实际文件事件处理
# ===========================================================

class _KyloproEventHandler(FileSystemEventHandler):
    """接收 watchdog 事件，放入 asyncio 队列。"""

    def __init__(self, queue: asyncio.Queue) -> None:
        super().__init__()
        self._queue = queue
        self._loop = asyncio.get_event_loop()

    def _enqueue(self, event_type: str, path: str) -> None:
        self._loop.call_soon_threadsafe(
            self._queue.put_nowait,
            {"type": event_type, "path": path, "time": datetime.now()},
        )

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue("created", event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue("modified", event.src_path)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._enqueue("deleted", event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._enqueue("moved", f"{event.src_path} -> {event.dest_path}")


# ===========================================================
# 主类
# ===========================================================

class FileMonitor:
    """
    哨兵眼文件监控器。

    Args:
        watch_path:       监控的目录路径
        ollama_summarize: 是否用本地 Ollama 生成文件摘要（默认 True）
        alert_on_delete:  删除事件是否告警（默认 True）
        alert_on_modify:  修改事件是否告警（默认 False，避免刷屏）
        ignore_patterns:  忽略的文件名模式列表
    """

    def __init__(
        self,
        watch_path: str | Path,
        ollama_summarize: bool = True,
        alert_on_delete: bool = True,
        alert_on_modify: bool = False,
        ignore_patterns: list[str] | None = None,
    ) -> None:
        self.watch_path = Path(watch_path)
        self.ollama_summarize = ollama_summarize
        self.alert_on_delete = alert_on_delete
        self.alert_on_modify = alert_on_modify
        self.ignore_patterns = ignore_patterns or [
            ".tmp", "~$", ".swp", "desktop.ini", "Thumbs.db",
        ]

        if not WATCHDOG_AVAILABLE:
            raise RuntimeError("请先安装 watchdog: pip install watchdog>=4.0.0")

        # 延迟 import notifier（避免循环依赖）
        from skills.telegram_notify.notify import TelegramNotifier
        self._notifier = TelegramNotifier()

        self._queue: asyncio.Queue = asyncio.Queue()
        self._observer = Observer()

    def _should_ignore(self, path: str) -> bool:
        """判断文件是否应该被忽略。"""
        return any(pat in path for pat in self.ignore_patterns)

    async def _handle_event(self, event: dict) -> None:
        """处理单个文件事件：摘要 + 推送告警。"""
        evt_type = event["type"]
        path = event["path"]
        evt_time = event["time"].strftime("%H:%M:%S")

        if self._should_ignore(path):
            return

        # 根据设置决定是否处理 modify 事件
        if evt_type == "modified" and not self.alert_on_modify:
            return
        if evt_type == "deleted" and not self.alert_on_delete:
            return

        filename = Path(path).name
        logger.info("[SENTINEL] {} - {}", evt_type.upper(), filename)

        # 生成摘要（仅 created/modified 类型，且文件还存在）
        summary = ""
        if evt_type in ("created", "modified") and Path(path).exists():
            preview = _read_file_preview(Path(path))
            if self.ollama_summarize and not preview.startswith("["):
                summary = await _ollama_summarize(preview, filename)
            elif preview.startswith("["):
                summary = preview

        # 构建告警消息
        icon = {"created": "NEW", "modified": "MOD", "deleted": "DEL", "moved": "MV"}.get(evt_type, "?")
        msg = (
            f"[{icon}] <b>哨兵眼告警</b> {evt_time}\n\n"
            f"<b>{filename}</b>\n"
            f"路径：{path}"
        )
        if summary:
            msg += f"\n\n摘要：{summary}"

        await self._notifier.send(msg)

    async def start(self) -> None:
        """启动文件监控（阻塞，Ctrl+C 停止）。"""
        if not self.watch_path.exists():
            raise FileNotFoundError(f"监控目录不存在: {self.watch_path}")

        handler = _KyloproEventHandler(self._queue)
        self._observer.schedule(handler, str(self.watch_path), recursive=True)
        self._observer.start()

        logger.info("[SENTINEL] 开始监控: {}", self.watch_path)
        await self._notifier.send(
            f"[SENTINEL] 哨兵眼已启动\n"
            f"监控目录：{self.watch_path}\n"
            f"Ollama 摘要：{'开启' if self.ollama_summarize else '关闭'}"
        )

        try:
            while True:
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                    await self._handle_event(event)
                except asyncio.TimeoutError:
                    continue
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            self._observer.stop()
            self._observer.join()
            logger.info("[SENTINEL] 监控已停止")


# ===========================================================
# CLI 入口
# ===========================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kylopro 哨兵眼 — 文件监控")
    parser.add_argument("--path", required=True, help="要监控的目录路径")
    parser.add_argument("--no-summarize", action="store_true", help="关闭 Ollama 摘要")
    parser.add_argument("--alert-modify", action="store_true", help="修改事件也告警")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    monitor = FileMonitor(
        watch_path=args.path,
        ollama_summarize=not args.no_summarize,
        alert_on_modify=args.alert_modify,
    )

    asyncio.run(monitor.start())
