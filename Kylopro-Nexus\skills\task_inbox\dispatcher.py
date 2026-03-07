"""
Kylopro 任务调度器 (Task Dispatcher)
====================================
将解析后的结构化子任务分发给对应技能执行。

路由表：
  action         → skill
  create_file    → IDEBridge.write_file()
  modify_file    → IDEBridge.read_file() + Provider.chat() + IDEBridge.write_file()
  run_command    → IDEBridge.run_command()
  browse_url     → WebPilot.navigate_and_brief()
  rpa_action     → VisionRPA（预留）
  analyze        → KyloproProvider.chat()
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass


class TaskDispatcher:
    """
    子任务调度器。

    接收 parser 输出的结构化任务清单，
    逐个执行子任务并记录结果。

    Args:
        workspace:   项目工作目录（传给 IDEBridge）
        results_dir: 执行结果存储目录
    """

    def __init__(
        self,
        workspace: str | Path,
        results_dir: str | Path | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.results_dir = Path(results_dir) if results_dir else (
            self.workspace / "data" / "inbox" / "results"
        )
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # 延迟初始化各技能（避免循环 import）
        self._ide_bridge = None
        self._provider = None

    def _get_ide_bridge(self):
        """延迟初始化 IDEBridge。"""
        if self._ide_bridge is None:
            from skills.ide_bridge.bridge import IDEBridge
            self._ide_bridge = IDEBridge(self.workspace)
        return self._ide_bridge

    def _get_provider(self):
        """延迟初始化 KyloproProvider。"""
        if self._provider is None:
            from core.provider import KyloproProvider
            self._provider = KyloproProvider()
        return self._provider

    def _get_agent_loop(self):
        """从全局单例 engine 中获取 AgentLoop。"""
        try:
            from core.engine import get_engine
            return get_engine()._get_agent_loop()
        except Exception as e:
            logger.warning(f"无法获取 AgentLoop: {e}")
            return None

    async def execute_all(
        self,
        task_data: dict[str, Any],
        task_id: str = "",
        on_progress: Any = None,
        check_interrupt: Any = None,
    ) -> dict[str, Any]:
        """
        执行全部子任务，返回汇总结果。

        Args:
            task_data:   parser 输出的结构化任务字典
            task_id:     任务 ID（用于结果文件命名）
            on_progress: 可选回调 async fn(subtask_id, status, message)

        Returns:
            {
              "title": "...",
              "total": N,
              "success": M,
              "failed": K,
              "results": [{"id", "action", "status", "output"}, ...]
            }
        """
        subtasks = task_data.get("subtasks", [])
        title = task_data.get("title", "未命名任务")

        logger.info("[DISPATCH] 开始执行任务「{}」— {} 个子任务", title, len(subtasks))

        results = []
        success_count = 0
        failed_count = 0

        for st in subtasks:
            if check_interrupt and check_interrupt():
                logger.warning("[DISPATCH] 任务执行被中断 (check_interrupt=True)")
                break
                
            st_id = st.get("id", 0)
            action = st.get("action", "analyze")
            target = st.get("target", "")
            detail = st.get("detail", "")

            logger.info("[DISPATCH] 子任务 #{}: {} → {}", st_id, action, target or detail[:50])

            if on_progress:
                await on_progress(st_id, "executing", f"正在执行: {action}")

            try:
                output = await self._execute_one(action, target, detail, task_data)
                results.append({
                    "id":     st_id,
                    "action": action,
                    "target": target,
                    "status": "success",
                    "output": str(output)[:500],
                })
                success_count += 1
                logger.info("[DISPATCH] 子任务 #{} 完成 ✅", st_id)

                if on_progress:
                    await on_progress(st_id, "done", f"完成: {action}")

            except Exception as e:
                results.append({
                    "id":     st_id,
                    "action": action,
                    "target": target,
                    "status": "failed",
                    "output": str(e)[:500],
                })
                failed_count += 1
                logger.error("[DISPATCH] 子任务 #{} 失败 ❌: {}", st_id, e)

                if on_progress:
                    await on_progress(st_id, "failed", f"失败: {e}")

        # 汇总
        summary = {
            "title":   title,
            "total":   len(subtasks),
            "success": success_count,
            "failed":  failed_count,
            "results": results,
            "timestamp": datetime.now().isoformat(),
        }

        # 保存结果
        if task_id:
            result_file = self.results_dir / f"{task_id}.json"
            result_file.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("[DISPATCH] 结果已保存: {}", result_file)

        return summary

    async def _execute_one(
        self,
        action: str,
        target: str,
        detail: str,
        task_data: dict[str, Any],
    ) -> str:
        """执行单个子任务，返回输出字符串。"""

        if action == "create_file":
            return await self._do_create_file(target, detail, task_data)

        elif action == "modify_file":
            return await self._do_modify_file(target, detail, task_data)

        elif action == "run_command":
            return await self._do_run_command(target, detail)

        elif action == "browse_url":
            return await self._do_browse_url(target, detail)

        elif action == "rpa_action":
            return await self._do_rpa_action(target, detail)

        elif action == "rpa_agent":
            return await self._do_rpa_agent(target, detail)

        elif action == "analyze":
            return await self._do_analyze(detail)

        else:
            raise ValueError(f"未知的 action 类型: {action}")

    # -----------------------------------------------------------
    # 各 action 处理方法
    # -----------------------------------------------------------

    async def _do_create_file(
        self, target: str, detail: str, task_data: dict[str, Any]
    ) -> str:
        """创建文件：用 LLM 生成内容 → IDEBridge 写入。"""
        bridge = self._get_ide_bridge()

        # 确定文件路径
        file_path = target or self._extract_filename(detail)
        if not file_path:
            raise ValueError(f"无法确定要创建的文件路径，detail: {detail}")

        # 如果 detail 中已经包含完整内容（含代码），直接写
        if self._looks_like_code(detail):
            content = detail
        else:
            # 用 LLM 生成文件内容
            is_python = file_path.endswith(".py")
            content = await self._generate_code(
                f"请根据以下需求生成文件 `{file_path}` 的完整内容：\n{detail}\n\n"
                f"直接输出代码内容，不要加 markdown 代码块标记。",
                validate_python=is_python
            )

        bridge.write_file(file_path, content)
        return f"已创建文件: {file_path} ({len(content)} 字符)"

    async def _do_modify_file(
        self, target: str, detail: str, task_data: dict[str, Any]
    ) -> str:
        """修改文件：优先用 AgentLoop 进行自主修改。"""
        file_path = target or self._extract_filename(detail)
        if not file_path:
            raise ValueError(f"无法确定要修改的文件路径，detail: {detail}")

        agent = self._get_agent_loop()
        if agent:
            try:
                # 显式告知这是修改文件任务
                prompt = f"请作为 Kylopro，修改文件 `{file_path}`。需求如下：\n\n{detail}\n\n" \
                         f"你可以先读取文件内容，然后进行修改。完成后请回复‘修改已完成’。"
                result = await agent.process_direct(
                    content=prompt,
                    session_key=f"inbox:modify:{file_path}",
                    channel="inbox",
                    chat_id="developer",
                )
                return f"Agent 修改结果:\n{result}"
            except Exception as e:
                logger.warning(f"AgentLoop 修改失败 ({e})，降级到 procedural 模式")

        # 原有的 procedural 修改逻辑
        bridge = self._get_ide_bridge()
        # ... (rest of original logic)

        # 用 LLM 生成修改后的版本
        is_python = file_path.endswith(".py")
        modified = await self._generate_code(
            f"以下是文件 `{file_path}` 的当前内容：\n\n{original}\n\n"
            f"请根据以下需求修改该文件：\n{detail}\n\n"
            f"输出修改后的完整文件内容，不要加 markdown 代码块标记。",
            validate_python=is_python
        )

        bridge.write_file(file_path, modified)
        return f"已修改文件: {file_path} ({len(modified)} 字符)"

    async def _do_run_command(self, target: str, detail: str) -> str:
        """执行 shell 命令。"""
        bridge = self._get_ide_bridge()

        command = target or detail
        # 安全检查：不执行包含危险关键词的命令
        BLOCKED = ["rm -rf", "del /f /s", "format c:", "rd /s /q"]
        if any(bad in command.lower() for bad in BLOCKED):
            raise ValueError(f"命令被安全策略拦截: {command}")

        result = await bridge.run_command(command, timeout=60)
        output = result.get("stdout", "")
        stderr = result.get("stderr", "")
        if result.get("success"):
            return f"命令执行成功:\n{output[:300]}"
        else:
            return f"命令执行失败:\nstdout: {output[:200]}\nstderr: {stderr[:200]}"

    async def _do_browse_url(self, target: str, detail: str) -> str:
        """浏览网页并返回 DOM 简报。"""
        url = target or detail
        if not url.startswith("http"):
            url = f"https://{url}"

        try:
            from skills.web_pilot.pilot import WebPilot
            async with WebPilot(headless=True) as pilot:
                brief = await pilot.navigate_and_brief(url)
                return f"网页简报 ({url}):\n{brief[:400]}"
        except Exception as e:
            return f"网页访问失败 ({url}): {e}"

    async def _do_rpa_action(self, target: str, detail: str) -> str:
        """桌面 RPA 操作（基础截图）。"""
        try:
            from skills.vision_rpa.vision import VisionRPA
            rpa = VisionRPA()
            # 目前只支持截图汇报
            ok = await rpa.screenshot_to_telegram(f"RPA 任务: {detail[:30]}")
            return "桌面截图已推送 Telegram" if ok else "截图推送失败"
        except Exception as e:
            return f"RPA 操作失败: {e}"

    async def _do_rpa_agent(self, target: str, detail: str) -> str:
        """运行高阶全自动桌面控制 Agent。"""
        try:
            from skills.vision_rpa.agent import DesktopAgent
            agent = DesktopAgent(workspace=str(self.workspace), max_steps=15)
            goal = detail
            if target:
                goal = f"{target} - {detail}"
                
            success = await agent.run_task(goal)
            return "DesktopAgent 自动驾驶任务完成" if success else "DesktopAgent 任务超时或失败"
        except Exception as e:
            return f"RPA Agent 运行崩溃: {str(e)}"

    async def _do_analyze(self, detail: str) -> str:
        """用 AgentLoop 进行分析（支持工具调用）。"""
        agent = self._get_agent_loop()
        if agent:
            try:
                # 显式告知这是分析任务
                prompt = f"请作为 Kylopro，对以下内容进行深度分析（你可以使用读文件或搜索工具）：\n\n{detail}"
                result = await agent.process_direct(
                    content=prompt,
                    session_key="inbox:analyze",
                    channel="inbox",
                    chat_id="analyzer",
                )
                return f"Agent 分析结果:\n{result}"
            except Exception as e:
                logger.warning(f"AgentLoop 分析失败 ({e})，降级到普通对话")
        
        provider = self._get_provider()
        result = await provider.chat(
            messages=[{"role": "user", "content": detail}],
            task_type="auto",
        )
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        return f"普通分析结果:\n{content[:400]}"

    # -----------------------------------------------------------
    # 辅助方法
    # -----------------------------------------------------------

    async def _generate_code(self, prompt: str, validate_python: bool = False) -> str:
        """调用 LLM 生成代码内容。"""
        provider = self._get_provider()
        
        # 尝试最多 3 次
        for attempt in range(3):
            result = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                task_type="code",
                max_tokens=8192,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
    
            # 清理可能的 markdown 代码块包装
            content = self._strip_code_fences(content)
            
            # 如果不要求验证，直接返回
            if not validate_python:
                return content
                
            # 要求验证 Python 语法
            try:
                # 尝试编译以检查语法错误
                compile(content, "<generated_code>", "exec")
                return content  # 校验通过
            except SyntaxError as e:
                logger.warning(f"[_generate_code] 语法校验失败 (第 {attempt+1} 次尝试): {e}")
                if attempt < 2:
                    prompt += f"\n\n注意：你刚才生成的代码有语法错误：\n{e}\n请修正错误并重新生成完整的正确代码。"
                else:
                    logger.error("代码生成 3 次重试仍有语法错误，直接返回最后一次的结果。")
                    return content
                    
        return ""

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """去掉 LLM 输出中的 markdown 代码块标记。"""
        import re
        # 去掉 <think>...</think>
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = text.strip()
        # 去掉 ```xxx\n...\n```
        match = re.match(r"```\w*\n(.*)\n```$", text, re.DOTALL)
        if match:
            return match.group(1)
        return text

    @staticmethod
    def _extract_filename(text: str) -> str:
        """从描述文本中提取文件名。"""
        import re
        # 匹配 `filename.ext` 或 filename.ext
        match = re.search(r"`([a-zA-Z0-9_/\\.-]+\.\w+)`", text)
        if match:
            return match.group(1)
        match = re.search(r"([a-zA-Z0-9_/\\-]+\.\w{1,5})", text)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _looks_like_code(text: str) -> bool:
        """判断文本是否看起来像代码内容。"""
        code_indicators = [
            "def ", "class ", "import ", "from ", "print(",
            "function ", "const ", "var ", "let ",
            "#!/", "<?php", "<html", "SELECT ",
        ]
        return any(indicator in text for indicator in code_indicators)

    def format_report(self, summary: dict[str, Any]) -> str:
        """将执行结果格式化为 Telegram 可读的 HTML 报告。"""
        title = summary.get("title", "未命名")
        total = summary.get("total", 0)
        success = summary.get("success", 0)
        failed = summary.get("failed", 0)
        results = summary.get("results", [])

        icon = "✅" if failed == 0 else "⚠️"

        lines = [
            f"{icon} <b>任务完成报告</b>",
            f"",
            f"<b>{title}</b>",
            f"总计: {total} | 成功: {success} | 失败: {failed}",
            f"",
        ]

        for r in results[:10]:  # 最多显示 10 个
            st_icon = "✅" if r["status"] == "success" else "❌"
            output_preview = r.get("output", "")[:80]
            lines.append(f"{st_icon} #{r['id']} {r['action']}: {output_preview}")

        return "\n".join(lines)
