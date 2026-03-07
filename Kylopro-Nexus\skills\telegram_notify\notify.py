"""
Kylopro Telegram 主动推送技能
==============================
让 Kylopro 主动向你的 Telegram 发送消息。

密钥来源优先级（高到低）：
  1. .env 中的 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
  2. ~/.nanobot/config.json 中的 channels.telegram

调用方式：
  from skills.telegram_notify.notify import TelegramNotifier
  notifier = TelegramNotifier()
  await notifier.send("你好！")
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _load_telegram_config() -> tuple[str, str]:
    """
    读取 Bot Token 和 Chat ID。
    优先 .env，其次 ~/.nanobot/config.json。
    """
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        # 从 nanobot config 读取
        config_path = Path.home() / ".nanobot" / "config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                tg  = cfg.get("channels", {}).get("telegram", {})
                if not token:
                    token = tg.get("token", "")
                if not chat_id:
                    # allowFrom 第一个元素作为目标 chat_id
                    allow = tg.get("allowFrom", [])
                    if allow:
                        chat_id = str(allow[0])
            except Exception as e:
                logger.warning("读取 nanobot config 中的 Telegram 配置失败: {}", e)

    return token, chat_id


class TelegramNotifier:
    """Kylopro 的 Telegram 主动推送器。"""

    def __init__(self) -> None:
        self.token, self.chat_id = _load_telegram_config()
        if not self.token:
            logger.warning("Telegram Bot Token 未配置，推送功能不可用")
        if not self.chat_id:
            logger.warning("Telegram Chat ID 未配置，推送功能不可用")

        # 轮询相关状态
        self._is_polling = False
        self._poll_task = None
        self._last_update_id = 0
        self._message_handler: Callable[[str], bool] | None = None

    @property
    def _configured(self) -> bool:
        return bool(self.token and self.chat_id)

    async def send(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        发送纯文本消息。

        Args:
            text:       消息内容（支持 HTML 格式）
            parse_mode: "HTML" | "Markdown" | "MarkdownV2"

        Returns:
            True 表示发送成功
        """
        if not self._configured:
            logger.error("Telegram 未配置，无法发送消息")
            return False

        url     = TELEGRAM_API.format(token=self.token)
        payload = {
            "chat_id":    self.chat_id,
            "text":       text,
            "parse_mode": parse_mode,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                logger.info("✅ Telegram 推送成功: {}", text[:50])
                return True
        except httpx.HTTPStatusError as e:
            logger.error("Telegram API 错误: {} — {}", e.response.status_code, e.response.text)
        except httpx.RequestError as e:
            logger.error("Telegram 网络错误: {}", e)
        return False

    async def send_alert(self, title: str, detail: str) -> bool:
        """
        发送告警消息（带醒目格式）。

        Args:
            title:  告警标题
            detail: 告警详情
        """
        msg = (
            f"⚠️ <b>[Kylopro 告警]</b>\n\n"
            f"<b>{title}</b>\n"
            f"{detail}"
        )
        return await self.send(msg)

    async def send_report(self, title: str, items: list[str]) -> bool:
        """
        发送汇报消息（列表格式）。

        Args:
            title: 报告标题
            items: 汇报条目列表
        """
        body  = "\n".join(f"  • {item}" for item in items)
        msg   = (
            f"📋 <b>[Kylopro 汇报]</b>\n\n"
            f"<b>{title}</b>\n\n"
            f"{body}"
        )
        return await self.send(msg)

    async def send_task_done(self, task_name: str, summary: str = "") -> bool:
        """任务完成通知。"""
        msg = f"✅ <b>任务完成</b>：{task_name}"
        if summary:
            msg += f"\n\n{summary}"
        return await self.send(msg)

    # ===========================================================
    # 消息接收功能 (Polling)
    # ===========================================================

    def set_handler(self, handler: Callable[[str], bool]) -> None:
        """设置消息处理回调函数 (返回 True 表示已接管消息)"""
        self._message_handler = handler

    async def start_polling(self) -> None:
        """启动后台长轮询，监听传入消息"""
        if not self._configured:
            logger.warning("Telegram 未配置，无法启动消息监听")
            return
            
        if self._is_polling:
            return
            
        self._is_polling = True
        logger.info("👂 Telegram 消息监听已启动")
        
        import asyncio
        self._poll_task = asyncio.create_task(self._poll_updates())

    def stop_polling(self) -> None:
        """停止轮询"""
        self._is_polling = False
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
            logger.info("⏹ Telegram 消息监听已停止")

    async def _poll_updates(self) -> None:
        """后台轮询循环"""
        import httpx
        import asyncio
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        
        # 使用单独的 Client，避免与发送消息冲突
        async with httpx.AsyncClient(timeout=35.0) as client:
            while self._is_polling:
                try:
                    payload = {
                        "offset": self._last_update_id + 1,
                        "timeout": 30, # 长轮询超时 30 秒
                        "allowed_updates": ["message"]
                    }
                    
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("ok"):
                            for update in data.get("result", []):
                                self._last_update_id = update["update_id"]
                                
                                msg_obj = update.get("message", {})
                                text = msg_obj.get("text", "").strip()
                                
                                # 只处理授权的 Chat ID 的消息
                                str_chat_id = str(msg_obj.get("chat", {}).get("id", ""))
                                if text and str_chat_id == self.chat_id:
                                    logger.info(f"📩 收到 Telegram 消息: {text}")
                                    if self._message_handler:
                                        # 非阻塞处理
                                        asyncio.create_task(self._dispatch_message(text))
                                        
                except asyncio.CancelledError:
                    break
                except httpx.ReadTimeout:
                    pass # 长轮询正常超时
                except Exception as e:
                    logger.debug(f"Telegram polling 异常: {e}")
                    await asyncio.sleep(5)
                    
    async def _dispatch_message(self, text: str) -> None:
        """分发消息到处理器"""
        if self._message_handler:
            try:
                # 兼容异步和同步的 handler
                import asyncio
                if asyncio.iscoroutinefunction(self._message_handler):
                    await self._message_handler(text)
                else:
                    self._message_handler(text)
            except Exception as e:
                logger.error(f"处理 Telegram 消息失败: {e}")


# ===========================================================
# 便捷函数（直接调用，无需实例化）
# ===========================================================

async def send_message(text: str) -> bool:
    """快速发送 Telegram 消息（便捷函数）。"""
    notifier = TelegramNotifier()
    return await notifier.send(text)


async def send_alert(title: str, detail: str) -> bool:
    """快速发送告警（便捷函数）。"""
    notifier = TelegramNotifier()
    return await notifier.send_alert(title, detail)


# ===========================================================
# CLI 测试入口
# ===========================================================

if __name__ == "__main__":
    import asyncio

    async def _test() -> None:
        notifier = TelegramNotifier()
        print(f"Bot Token: {'✅ 已配置' if notifier.token else '❌ 未配置'}")
        print(f"Chat ID  : {'✅ ' + notifier.chat_id if notifier.chat_id else '❌ 未配置'}")

        if notifier._configured:
            ok = await notifier.send(
                "🤖 <b>Kylopro 技能测试</b>\n\n"
                "✅ telegram_notify 技能已激活！\n"
                "你的数字分身 Kylopro 现在可以主动联系你了。"
            )
            print(f"\n测试推送: {'✅ 成功' if ok else '❌ 失败'}")
        else:
            print("\n⚠️ 配置不完整，跳过推送测试")

    asyncio.run(_test())
