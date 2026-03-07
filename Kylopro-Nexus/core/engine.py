"""
Kylopro Engine - 精简版
========================
职责：
1. 初始化 KyloproProvider（智能路由到不同 AI 模型）
2. 注册 Kylopro 自定义 skills 和 tools
3. 启动 nanobot gateway（Telegram 连接）

注意：消息处理、并发、队列全部交给 nanobot AgentLoop，不在这里实现。
不再有 process() 方法——消息路由是 nanobot 框架的职责。
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# 确保可以 import nanobot（无论从哪里运行都能找到）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)


class KyloproEngine:
    """
    Kylopro 核心引擎 - 精简版

    只做三件事：
    1. 初始化 provider（负责选择用哪个 AI 模型）
    2. 注册所有自定义 skills 和 tools
    3. 启动 nanobot gateway（Telegram 等连接）

    不再自己处理消息路由——这是 nanobot 框架的职责。
    消息的并发处理、队列管理全部由 nanobot AgentLoop 负责。
    """

    def __init__(self):
        """初始化引擎，加载 provider 和 skills"""
        logger.info("🚀 KyloproEngine 初始化中...")

        # 1. 加载配置（.env 文件）
        self._load_config()

        # 2. 初始化 provider（智能路由到不同 AI 模型）
        self._init_provider()

        # 3. 扫描并记录 skills 目录（实际注册在 start() 里进行）
        self._load_skills()

        logger.info("✅ KyloproEngine 初始化完成")

    def _load_config(self):
        """加载环境变量配置（从 .env 文件）"""
        try:
            from dotenv import load_dotenv
            # .env 文件在 Kylopro-Nexus 目录下（即本文件的上一级目录）
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                logger.info(f"✅ 已加载配置文件: {env_path}")
            else:
                # 如果没有 .env，尝试从环境变量直接读取（Docker/CI 场景）
                logger.warning(f"⚠️ 未找到 .env 文件: {env_path}，将使用系统环境变量")
        except ImportError:
            logger.warning("⚠️ python-dotenv 未安装，跳过 .env 加载")

    def _init_provider(self):
        """
        初始化 KyloproProvider。
        Provider 负责智能路由：决定用 DeepSeek、GLM-4V、Ollama 还是 OpenRouter。
        """
        try:
            from core.provider import KyloproProvider
            self.provider = KyloproProvider()
            logger.info("✅ KyloproProvider 初始化成功")
        except Exception as e:
            logger.error(f"❌ KyloproProvider 初始化失败: {e}")
            raise

    def _load_skills(self):
        """
        扫描 skills 目录，记录可用的自定义技能列表。
        skills 是 Kylopro 的特殊能力，比如：文件监控、GitHub 管理、任务收件箱等。
        实际的 skill 注册在 nanobot AgentLoop 初始化时进行。
        """
        skills_dir = Path(__file__).parent.parent / "skills"
        if not skills_dir.exists():
            logger.warning(f"⚠️ skills 目录不存在: {skills_dir}")
            self.loaded_skills = []
            return

        self.loaded_skills = []
        for skill_dir in sorted(skills_dir.iterdir()):
            # 只识别带 __init__.py 的子目录（标准 Python 包格式）
            if skill_dir.is_dir() and (skill_dir / "__init__.py").exists():
                self.loaded_skills.append(skill_dir.name)
                logger.info(f"📦 已发现 skill: {skill_dir.name}")

        logger.info(f"✅ 共发现 {len(self.loaded_skills)} 个 skills")

    async def start(self):
        """
        启动 nanobot gateway（Telegram 连接）。

        开机自检和招呼放在这里，作为 gateway 启动后的 hook。
        nanobot 框架负责所有消息的并发处理，不需要我们自己实现。
        """
        logger.info("🌐 正在启动 nanobot gateway...")

        try:
            # 尝试导入 nanobot 的 gateway/CLI 启动器
            # nanobot 框架会自动处理 Telegram/WhatsApp 等连接
            from nanobot.cli.commands import run_gateway

            # 先执行开机自检（告知用户各 AI 接口状态）
            await self._startup_check()

            # 启动 gateway（这会阻塞直到程序退出）
            await run_gateway(provider=self.provider)

        except ImportError:
            # 如果 nanobot 的 gateway 接口不同，使用备用方案
            logger.info("nanobot gateway 接口未找到，使用备用启动方式...")
            await self._start_gateway_fallback()

    async def _startup_check(self):
        """
        开机自检：测试各个 AI 接口是否可用。
        这相当于开机问候，告知用户系统状态，但不会阻塞启动。
        """
        logger.info("🔍 开机自检中...")
        try:
            status = await self.provider.test_connection()
            logger.info(f"自检结果: {status}")
        except Exception as e:
            # 自检失败不影响系统启动，只记录警告
            logger.warning(f"⚠️ 开机自检失败（不影响启动）: {e}")

    async def _start_gateway_fallback(self):
        """
        备用 gateway 启动方式。
        如果 nanobot 接口有变化，用这个方法作为后备，保持进程存活。
        """
        logger.info("🔄 使用备用方式启动，等待连接...")
        # 保持运行，等待 nanobot gateway 连接
        while True:
            await asyncio.sleep(1)

    async def run_cli(self):
        """
        CLI 模式：在终端直接对话，用于本地测试（无需 Telegram）。
        直接使用 nanobot 的 CLI 模式。
        """
        logger.info("💻 启动 CLI 模式...")
        try:
            from nanobot.cli.commands import run_cli as nanobot_run_cli
            await nanobot_run_cli(provider=self.provider)
        except Exception as e:
            logger.error(f"CLI 模式启动失败: {e}")
            # 简单的备用 CLI（用于调试）
            await self._simple_cli()

    async def _simple_cli(self):
        """简单的备用 CLI 模式（当 nanobot CLI 不可用时使用）"""
        print("Kylopro CLI 模式（备用）")
        print("输入 'quit' 退出")
        while True:
            try:
                user_input = input("\nYou > ").strip()
                if user_input.lower() in ('quit', 'exit', 'q'):
                    break
                if not user_input:
                    continue

                # 直接调用 provider 获取回复
                messages = [{"role": "user", "content": user_input}]
                response = await self.provider.chat(messages)
                # provider.chat() 返回 LLMResponse 对象，取 .content 字段
                content = getattr(response, 'content', str(response))
                print(f"\nKylo > {content}")

            except KeyboardInterrupt:
                print("\n\n再见！")
                break
            except Exception as e:
                print(f"错误: {e}")


async def main():
    """主入口：根据命令行参数决定启动模式"""
    engine = KyloproEngine()

    # 根据命令行参数决定启动模式
    # 例如：python -m core.engine cli → CLI 测试模式
    # 例如：python -m core.engine     → gateway 模式（Telegram）
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        await engine.run_cli()
    else:
        await engine.start()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    asyncio.run(main())
