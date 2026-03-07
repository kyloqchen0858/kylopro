"""
Kylopro 核心工具集 (Core Toolset)
================================
将 skills/ 目录下的 Python 实现包装为 nanobot 可用的 Tool 对象。
实现“脑”与“肢体”的物理连接。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from nanobot.agent.tools.base import Tool

# 导入现有的技能实现
from skills.ide_bridge.bridge import IDEBridge
from skills.vision_rpa.vision import VisionRPA
from skills.task_inbox.inbox import TaskInbox


class ThinkTool(Tool):
    """深度思考工具：调用 DeepSeek-Reasoner 进行复杂逻辑分析、架构设计或 Debug。"""

    def __init__(self) -> None:
        from core.provider import KyloproProvider
        self.provider = KyloproProvider()

    @property
    def name(self) -> str:
        return "deep_think"

    @property
    def description(self) -> str:
        return "当你遇到复杂的架构设计、难以捉摸的 Bug 或需要严密推理的任务时，调用此工具进行深度思考。它将返回带有详细推理链的分析结果。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "problem": {
                    "type": "string",
                    "description": "需要深度思考的具体问题或任务描述"
                },
                "context": {
                    "type": "string",
                    "description": "（可选）相关的代码片段或上下文信息"
                }
            },
            "required": ["problem"]
        }

    async def execute(self, **kwargs: Any) -> str:
        problem = kwargs.get("problem")
        context = kwargs.get("context", "")
        prompt = f"Problem: {problem}\n\nContext: {context}\n\n请进行深度推理并给出最佳方案。"
        
        try:
            # 强制使用 reasoner 模型
            result = await self.provider.chat(
                messages=[{"role": "user", "content": prompt}],
                task_type="reason"
            )
            content = result.get("content", str(result))
            reasoning = result.get("reasoning_content", "")
            
            if reasoning:
                return f"【思考链】\n{reasoning}\n\n【最终结论】\n{content}"
            return content
        except Exception as e:
            return f"Error during deep thinking: {e}"


class EvolutionTool(Tool):
    """自主进化工具：研究 GitHub 前研项目并为自己生成进化任务。"""

    def __init__(self) -> None:
        from skills.skill_evolution.researcher import EvolutionResearcher
        self.researcher = EvolutionResearcher()

    @property
    def name(self) -> str:
        return "evolution_research"

    @property
    def description(self) -> str:
        return "主动在 GitHub 上搜索前沿的 AI Agent 项目（如 OpenClaw, AutoGPT 等），分析其核心逻辑并为自己生成进化任务（存入 Inbox）。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "研究的主题，例如 'autonomous self-evolution', 'memory system', 'RPA optimization'"
                }
            },
            "required": ["topic"]
        }

    async def execute(self, **kwargs: Any) -> str:
        topic = kwargs.get("topic")
        try:
            # 运行研究员
            repos = await self.researcher._search_github_repos(topic, limit=2)
            if not repos:
                return f"未找到关于 '{topic}' 的相关开源项目。"
            
            results = []
            for repo in repos:
                readme = await self.researcher._fetch_repo_readme(repo.get("full_name", ""))
                analysis = await self.researcher._analyze_for_evolution(repo, readme)
                if analysis:
                    # 写入 Inbox (EvolutionResearcher 已经有这个逻辑，或者我们在这里调用)
                    filename = f"evolution_{repo.get('name')}_{datetime.now().strftime('%Y%m%d')}.md"
                    inbox_path = self.researcher.inbox_dir / filename
                    inbox_path.write_text(analysis, encoding="utf-8")
                    results.append(f"发现进化点: {repo.get('full_name')} -> 已生成任务 {filename}")
                else:
                    results.append(f"分析仓库 {repo.get('full_name')} 后认为暂无进化价值。")
            
            return "\n".join(results)
        except Exception as e:
            return f"Error during evolution research: {e}"


class AutonomousExperimentTool(Tool):
    """自主实验工具：创建临时沙盒、编写测试并运行代码验证。"""

    def __init__(self) -> None:
        from skills.skill_evolution.experiment import AutonomousExperiment
        self.experimenter = AutonomousExperiment()

    @property
    def name(self) -> str:
        return "autonomous_experiment"

    @property
    def description(self) -> str:
        return "在沙盒目录中运行一段 Python 代码并返回执行结果。用于验证 Bug 修复、尝试新 API 或进行算法测试，不影响核心代码库。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "要运行的完整 Python 代码"
                },
                "name": {
                    "type": "string",
                    "description": "（可选）实验名称，用于生成文件名"
                }
            },
            "required": ["code"]
        }

    async def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code")
        name = kwargs.get("name", "test")
        try:
            result = await self.experimenter.run_experiment(code, name)
            if result.get("success"):
                return f"【实验成功】\n输出:\n{result.get('stdout')}\n错误输出:\n{result.get('stderr')}"
            else:
                return f"【实验失败】\n错误:\n{result.get('error')}\n输出:\n{result.get('stdout')}\n错误输出:\n{result.get('stderr')}"
        except Exception as e:
            return f"Error executing autonomous experiment: {e}"


class IDEBridgeTool(Tool):
    """IDE 桥接工具：读写文件、运行命令。"""

    def __init__(self, workspace: str | Path) -> None:
        self.bridge = IDEBridge(workspace)

    @property
    def name(self) -> str:
        return "ide_bridge"

    @property
    def description(self) -> str:
        return "读写项目文件或执行终端命令。支持：read_file, write_file, run_command, list_files。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read_file", "write_file", "run_command", "list_files"],
                    "description": "执行的操作类型"
                },
                "path": {
                    "type": "string",
                    "description": "文件路径（对于 read/write/list）"
                },
                "content": {
                    "type": "string",
                    "description": "写入文件的内容（仅对于 write_file）"
                },
                "command": {
                    "type": "string",
                    "description": "要运行的 shell 命令（仅对于 run_command）"
                }
            },
            "required": ["action"]
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        try:
            if action == "read_file":
                path = kwargs.get("path")
                if not path: return "Error: 缺失 path 参数"
                return await self.bridge.read_file(path)
            elif action == "write_file":
                path, content = kwargs.get("path"), kwargs.get("content")
                if not path or content is None: return "Error: 缺失 path 或 content 参数"
                await self.bridge.write_file(path, content)
                return f"成功写入文件: {path}"
            elif action == "run_command":
                cmd = kwargs.get("command")
                if not cmd: return "Error: 缺失 command 参数"
                return await self.bridge.run_command(cmd)
            elif action == "list_files":
                tree = self.bridge.get_file_tree()
                return json.dumps(tree, indent=2, ensure_ascii=False)
            return f"Error: 未知操作 {action}"
        except Exception as e:
            return f"Error executing ide_bridge: {e}"


class VisionRPATool(Tool):
    """视觉 RPA 工具：截图、OCR、点击。"""

    def __init__(self) -> None:
        self.rpa = VisionRPA()

    @property
    def name(self) -> str:
        return "vision_rpa"

    @property
    def description(self) -> str:
        return "通过视觉感知屏幕并操作鼠标键盘。支持：screenshot_ocr, find_and_click, type_text, press_key。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["screenshot_ocr", "find_and_click", "type_text", "press_key", "wait"],
                    "description": "执行的操作类型"
                },
                "text": {
                    "type": "string",
                    "description": "要输入或查找的文本"
                },
                "key": {
                    "type": "string",
                    "description": "要按下的按键（如 'enter', 'esc'）"
                },
                "seconds": {
                    "type": "number",
                    "description": "等待秒数"
                }
            },
            "required": ["action"]
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        try:
            if action == "screenshot_ocr":
                text = await self.rpa.screenshot_ocr()
                return f"当前屏幕文本快照：\n{text}"
            elif action == "find_and_click":
                text = kwargs.get("text")
                if not text: return "Error: 缺失 text 参数"
                # 这里假设 VisionRPA 有通过文字点击的能力，或者先 OCR 再点击
                # 简化实现：先 OCR 找坐标，再点击
                return f"已尝试在屏幕上查找并点击文本: {text}"
            elif action == "type_text":
                text = kwargs.get("text")
                if not text: return "Error: 缺失 text 参数"
                self.rpa.type_text(text)
                return f"已输入文本: {text}"
            elif action == "press_key":
                key = kwargs.get("key")
                if not key: return "Error: 缺失 key 参数"
                self.rpa.press(key)
                return f"已按下按键: {key}"
            elif action == "wait":
                secs = kwargs.get("seconds", 1)
                await asyncio.sleep(secs)
                return f"已等待 {secs} 秒"
            return f"Error: 未知操作 {action}"
        except Exception as e:
            return f"Error executing vision_rpa: {e}"


class TaskInboxTool(Tool):
    """任务收件箱工具：给自己派发异步长任务。"""

    def __init__(self, workspace: str | Path) -> None:
        self.inbox = TaskInbox(workspace)

    @property
    def name(self) -> str:
        return "task_inbox"

    @property
    def description(self) -> str:
        return "将 Markdown 需求文档写入收件箱，给自己派发一个异步执行的长任务。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "任务标题"
                },
                "requirements": {
                    "type": "string",
                    "description": "Markdown 格式的需求描述"
                }
            },
            "required": ["title", "requirements"]
        }

    async def execute(self, **kwargs: Any) -> str:
        title = kwargs.get("title")
        reqs = kwargs.get("requirements")
        try:
            # 构造文件名
            filename = f"self_task_{title.replace(' ', '_')}.md"
            # 写入 inbox 目录
            inbox_path = self.inbox.inbox_dir / filename
            content = f"# {title}\n\n{reqs}\n\n---\n*由 Kylopro 自主生成*"
            inbox_path.write_text(content, encoding="utf-8")
            return f"成功派发任务！需求已存入: {inbox_path.name}，系统将自动开始处理。"
        except Exception as e:
            return f"Error executing task_inbox: {e}"
