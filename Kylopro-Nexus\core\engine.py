"""
Kylopro 主控循环
===============
封装 nanobot AgentLoop，注入双核路由 Provider，
自动加载 skills/ 目录，提供 CLI 交互入口。

使用方式：
    python -m core.engine
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from core.config import PROJECT_ROOT, SKILLS_DIR, DATA_DIR, load_nanobot_config


def _print_banner() -> None:
    """打印 Kylopro 启动横幅（身份信息）。"""
    print("""
╔══════════════════════════════════════════╗
║      🤖 Kylopro-Nexus  —  你的数字分身      ║
║  双核大脑: DeepSeek ⚡ + Ollama 🏠          ║
║  输入 /help 查看指令  |  /exit 退出          ║
╚══════════════════════════════════════════╝
""")

class KyloproEngine:
    """
    Kylopro 主控循环。
    """

    def __init__(self) -> None:
        from core.provider import KyloproProvider

        self.provider = KyloproProvider()
        self.config   = load_nanobot_config()
        self._loop: object | None = None   # nanobot AgentLoop（懒初始化）
        self._inbox = None                 # TaskInbox（按需初始化）
        self._inbox_task = None            # 后台监控 asyncio.Task
        
        # 启动时自动开启任务收件箱监控（后台静默运行）
        asyncio.create_task(self._auto_start_inbox())
        
        # 启动时执行自主自检与主动打招呼
        asyncio.create_task(self._startup_routine())

    async def _auto_start_inbox(self) -> None:
        """后台静默启动任务收件箱监控。"""
        try:
            await asyncio.sleep(2)
            inbox = self._get_inbox()
            if inbox:
                logger.info("🚀 自动启动任务收件箱监控 (Task Inbox)...")
                self._inbox_task = asyncio.create_task(inbox.start())
        except Exception as e:
            logger.warning(f"自动启动任务收件箱失败: {e}")

    async def _startup_routine(self) -> None:
        """开机自检、任务恢复并向主人打招呼。"""
        try:
            # 等待系统稍微稳定
            await asyncio.sleep(5)
            
            # 1. 执行技能自检
            from skills.skill_evolution.verifier import SkillVerifier
            verifier = SkillVerifier()
            report = await verifier.run_all(notify_telegram=False) # 我们统一在后面发招呼消息
            
            # 2. 检查任务进度（Inbox & Dispatcher 状态）
            inbox = self._get_inbox()
            pending_count = 0
            if inbox:
                # 获取待处理任务数
                inbox_dir = Path(inbox.inbox_dir)
                pending_count = len(list(inbox_dir.glob("*.md"))) + len(list(inbox_dir.glob("*.txt")))

            # 3. 构造打招呼消息
            status_emoji = "✅" if report["summary"]["fail"] == 0 else "⚠️"
            greeting = f"""
<b>🐈 Kylopro-Nexus 已上线</b>

{status_emoji} <b>系统自检完成</b>：
- 正常技能：{report['summary']['ok']} 项
- 异常/缺失：{report['summary']['fail']} 项
- 待处理任务：{pending_count} 个

<b>🧠 记忆状态</b>：
- 向量库：已加载
- 上次任务进度：已自动恢复监控

<i>“指挥官，我已经准备好继续进化了。有什么新指令吗？”</i>
"""
            # 4. 发送 Telegram 招呼
            from skills.telegram_notify.notify import TelegramNotifier
            notifier = TelegramNotifier()
            if notifier._configured:
                await notifier.send(greeting)
                logger.info("🚀 已向主人发送开机招呼消息")
                
        except Exception as e:
            logger.warning(f"开机 Routine 失败: {e}")

    def _get_agent_loop(self) -> object:
        """延迟初始化 nanobot AgentLoop。"""
        if self._loop is not None:
            return self._loop

        try:
            from nanobot.agent.loop import AgentLoop
            from nanobot.bus.queue import MessageBus
            from nanobot.agent.tools.web import WebSearchTool, WebFetchTool
            from core.tools import IDEBridgeTool, VisionRPATool, TaskInboxTool

            # 使用 Kylopro 自研的双核路由 Provider (DeepSeek + Ollama + Vision Slot)
            nanobot_provider = self.provider

            bus = MessageBus()
            DATA_DIR.mkdir(parents=True, exist_ok=True)

            self._loop = AgentLoop(
                bus        = bus,
                provider   = nanobot_provider,
                workspace  = PROJECT_ROOT,
                model      = None,  # 让 Provider 内部根据内容自动路由
                temperature = 0.1,
                max_tokens  = 8192,
            )
            
            from core.tools import IDEBridgeTool, VisionRPATool, TaskInboxTool, ThinkTool, EvolutionTool, AutonomousExperimentTool

            self._loop.tools.register(IDEBridgeTool(PROJECT_ROOT))
            self._loop.tools.register(VisionRPATool())
            self._loop.tools.register(TaskInboxTool(PROJECT_ROOT))
            self._loop.tools.register(ThinkTool())
            self._loop.tools.register(EvolutionTool())
            self._loop.tools.register(AutonomousExperimentTool())
            
            # 注册联网搜索和获取工具
            self._loop.tools.register(WebSearchTool())
            self._loop.tools.register(WebFetchTool())
            
            if hasattr(self._loop, "load_skills"):
                self._loop.load_skills(SKILLS_DIR)
                
            logger.info("nanobot AgentLoop 初始化完成")
        except ImportError as e:
            logger.error("nanobot 未安装: {}", e)
            raise

        return self._loop

    async def process(
        self,
        message: str,
        task_type: str = "auto",
        session_key: str = "cli:kylopro",
    ) -> str:
        """处理用户消息。"""
        messages = [{"role": "user", "content": message}]

        needs_tools = any(kw in message.lower() for kw in [
            "文件", "搜索", "运行", "执行", "代码", "安装", "自检", "技能", 
            "美化", "重构", "优化", "测试", "开发", "操作", "屏幕", "点击",
            "写", "生成", "改", "修复", "ide", "trae", "rpa", "vision"
        ])

        if task_type == "complex" or any(kw in message for kw in ["自己", "实验", "开发", "给我"]):
            needs_tools = True

        if needs_tools:
            try:
                agent_loop = self._get_agent_loop()
                response = await agent_loop.process_direct(
                    content     = message,
                    session_key = session_key,
                    channel     = "cli",
                    chat_id     = "kylopro",
                )
                return response
            except Exception as e:
                logger.warning("AgentLoop 失败 ({})，降级到双核路由", e)

        result = await self.provider.chat(
            messages  = messages,
            task_type = task_type,
        )
        return result.get("content", str(result))

    async def test_all(self) -> None:
        """测试连通性。"""
        result = await self.provider.test_connection()
        print(f"\n🔍 连通性测试:\n{result}\n")

    async def run_cli(self) -> None:
        """CLI 交互。"""
        _print_banner()
        await self.test_all()

        try:
            while True:
                user_input = await asyncio.to_thread(input, "You > ")
                if user_input.lower() in ("/exit", "/quit"): break
                if not user_input.strip(): continue
                
                print("Kylopro > ", end="", flush=True)
                result = await self.process(user_input)
                print(result)
        except (EOFError, KeyboardInterrupt):
            pass
        print("\n👋 已退出")

    def _get_inbox(self):
        if self._inbox is None:
            from skills.task_inbox.inbox import TaskInbox
            self._inbox = TaskInbox(workspace=PROJECT_ROOT)
        return self._inbox

# 单例
_INSTANCE: Optional[KyloproEngine] = None

def get_engine() -> KyloproEngine:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = KyloproEngine()
    return _INSTANCE

if __name__ == "__main__":
    engine = get_engine()
    asyncio.run(engine.run_cli())
