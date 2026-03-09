"""
Kylopro 配置加载器 (Config Loader)
================================
统一管理 .env, ~/.nanobot/config.json 以及 SOUL.md。
消除 provider.py 和 engine.py 的冗余。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

# 常量定义
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SKILLS_DIR = PROJECT_ROOT / "skills"
SOUL_FILE = PROJECT_ROOT / "SOUL.md"

def load_nanobot_config() -> dict[str, Any]:
    """读取 ~/.nanobot/config.json。"""
    config_path = Path.home() / ".nanobot" / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"读取 nanobot config 失败: {e}")
    return {}

def get_soul_prompt() -> str:
    """读取 SOUL.md 内容。"""
    if SOUL_FILE.exists():
        try:
            return SOUL_FILE.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"读取 SOUL.md 失败: {e}")
    return "你是一个名为 Kylopro 的高度自治数字分身。主动使用工具解决问题。"

def get_env_var(key: str, default: str = "") -> str:
    """获取环境变量，优先从 .env 读取。"""
    return os.getenv(key, default)
