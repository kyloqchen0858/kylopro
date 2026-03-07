"""
Kylopro 桌面自动驾驶代理 (Desktop Agent)
========================================
结合了屏幕感知 (EasyOCR) 与高级推理 (DeepSeek-Reasoner) 的闭环代理系统。
能够在无外设或有外设环境下，根据自然语言目标自主操作鼠标键盘。
"""

from __future__ import annotations

import asyncio
import re
import sys
from typing import Any

from loguru import logger

from core.provider import KyloproProvider
from skills.vision_rpa.vision import VisionRPA, capture_screen, get_ocr_reader
import numpy as np


class DesktopAgent:
    """
    全自动的计算机控制 Agent。
    
    循环过程:
    1. 感知：截屏 + OCR，提取带有坐标的可见文本（Semantic Snapshot）
    2. 推理：将文本快照连同当前目标发给大模型
    3. 行动：解析模型的标准输出指令并执行
    """
    
    def __init__(self, workspace: str, max_steps: int = 15) -> None:
        self.workspace = workspace
        self.max_steps = max_steps
        self.rpa = VisionRPA()
        self.provider = KyloproProvider()
        
        # Agent 的上下文记忆
        self.history: list[dict[str, str]] = []
        
        # 预热 OCR
        self._reader = get_ocr_reader()

    async def _perceive_screen(self) -> str:
        """获取当前屏幕的语义快照（带坐标的文本列表）。"""
        logger.info("[Agent] 正在感知屏幕...")
        
        try:
            img = capture_screen()
            img_np = np.array(img)
            
            raw_results = self._reader.readtext(img_np)
            
            # 将复杂的图像转化为结构化的一维文本
            snapshot_lines = []
            for box, text, conf in raw_results:
                if conf < 0.4:  # 过滤低置信度噪点
                    continue
                    
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                cx = int(sum(xs) / 4)
                cy = int(sum(ys) / 4)
                
                snapshot_lines.append(f"[{cx}, {cy}] {text}")
                
            snapshot = "\n".join(snapshot_lines)
            logger.debug(f"[Agent] 屏幕快照生成完毕 ({len(snapshot_lines)} 个元素)")
            return snapshot
            
        except Exception as e:
            logger.error("[Agent] 屏幕感知失败: {}", e)
            return "屏幕感知失败"

    def _build_system_prompt(self, goal: str) -> str:
        return f"""你是一个运行在 Windows 环境下的高阶桌面自动驾驶助理 (Desktop Agent)。
你的核心目标是: {goal}

# 你的视觉机制
由于你无法直接看到图片，我会每轮发给你当前屏幕的「语义快照」。
格式为：[X坐标, Y坐标] 屏幕上的文本
这代表在该坐标附近有一个可以点击的按钮或可阅读的文本。

# 你的输出指令集
你必须以严格的代码块格式输出你的操作，每轮只能输出一条核心指令！
可用的操作如下：
1. `CLICK(x, y)`: 左键单击对应坐标。
2. `DOUBLE_CLICK(x, y)`: 左键双击对应坐标。
3. `TYPE("text")`: 输入文本。注意：中文输入可能需要拼音或粘贴，尽量用英文或粘贴操作。
4. `HOTKEY("ctrl", "v")`: 发送组合快捷键。
5. `PRESS("enter")`: 按下单个按键（如 enter, esc, tab）。
6. `WAIT(seconds)`: 等待指定秒数（通常用于界面加载）。
7. `DONE("reason")`: 任务已完成，附带完成结果或理由。

# 思考过程
在你输出指令前，你可以且应该先进行思考，分析当前的屏幕状态是否符合预期，以及下一步该做什么。

请确保你的操作指令明确且唯一。例如：
我决定点击“发送”按钮：
```
CLICK(800, 600)
```
"""

    async def _execute_action(self, action_str: str) -> str:
        """解析并执行单条 Agent 指令。"""
        action_str = action_str.strip()
        logger.info("[Agent] 执行指令: {}", action_str)
        
        try:
            if action_str.startswith("CLICK("):
                match = re.search(r"CLICK\(\s*(\d+)\s*,\s*(\d+)\s*\)", action_str)
                if match:
                    x, y = int(match.group(1)), int(match.group(2))
                    self.rpa.move_to(x, y)
                    await asyncio.sleep(0.1)
                    self.rpa.click(x, y)
                    return f"已在 ({x}, {y}) 点击鼠标。"
                    
            elif action_str.startswith("DOUBLE_CLICK("):
                match = re.search(r"DOUBLE_CLICK\(\s*(\d+)\s*,\s*(\d+)\s*\)", action_str)
                if match:
                    x, y = int(match.group(1)), int(match.group(2))
                    self.rpa.move_to(x, y)
                    await asyncio.sleep(0.1)
                    self.rpa.double_click(x, y)
                    return f"已在 ({x}, {y}) 双击鼠标。"
                    
            elif action_str.startswith("TYPE("):
                # 匹配 TYPE("...")
                match = re.search(r'TYPE\("([^"]+)"\)', action_str)
                if not match:
                    match = re.search(r"TYPE\('([^']+)'\)", action_str)
                if match:
                    text = match.group(1)
                    # 中文输入处理：目前 rpa type 不好打中文，实际最好用 pyperclip 协助，这里简化
                    self.rpa.type_text(text)
                    return f"已输入文本: {text[:20]}..."
                    
            elif action_str.startswith("PRESS("):
                match = re.search(r'PRESS\("?([a-zA-Z0-9]+)"?\)', action_str)
                if match:
                    key = match.group(1).lower()
                    self.rpa.press(key)
                    return f"已按下按键: {key}"
                    
            elif action_str.startswith("HOTKEY("):
                # 提取参数: HOTKEY("ctrl", "v")
                keys = re.findall(r'["\']([^"\']+)["\']', action_str)
                if keys:
                    self.rpa.hotkey(*keys)
                    return f"已按下快捷键: {'+'.join(keys)}"
                    
            elif action_str.startswith("WAIT("):
                match = re.search(r"WAIT\(\s*(\d+)\s*\)", action_str)
                if match:
                    secs = int(match.group(1))
                    await asyncio.sleep(secs)
                    return f"已等待 {secs} 秒。"
                    
            elif action_str.startswith("DONE("):
                match = re.search(r'DONE\("?([^"]*)"?\)', action_str)
                reason = match.group(1) if match else "未提供理由"
                return f"!!DONE!! {reason}"
                
        except Exception as e:
            msg = f"操作执行异常: {e}"
            logger.error("[Agent] {}", msg)
            return msg
            
        return f"指令格式无法解析: {action_str}"

    def _extract_action(self, text: str) -> str:
        """从 LLM 回复中提取代码块内的动作指令。"""
        # 取最后一个代码块
        matches = re.findall(r"```(?:\w+)?\n?(.*?)\n?```", text, re.DOTALL)
        if matches:
            return matches[-1].strip()
        
        # 兜底：尝试找不带代码块的单行指令
        for line in reversed(text.splitlines()):
            line = line.strip()
            if any(line.startswith(x) for x in ["CLICK", "DOUBLE_CLICK", "TYPE", "PRESS", "HOTKEY", "WAIT", "DONE"]):
                return line
                
        return "WAIT(3)" # 默认等一会儿

    async def run_task(self, goal: str) -> bool:
        """
        开始执行自动驾驶任务主循环。
        
        Args:
            goal: 最终目标描述
        Returns:
            bool: 任务是否成功完成
        """
        sys_prompt = self._build_system_prompt(goal)
        self.history = [{"role": "system", "content": sys_prompt}]
        
        logger.info("[Agent] 启动桌面自动驾驶循环，目标: {}", goal)
        
        for step in range(1, self.max_steps + 1):
            logger.info("[Agent] === 第 {} 轮操作 ===", step)
            
            # 1. 感知
            snapshot = await self._perceive_screen()
            user_msg = f"当前屏幕状态：\n{snapshot}\n\n请输出下一步操作对应的严格指令。"
            self.history.append({"role": "user", "content": user_msg})
            
            # 2. 推理决策
            result = await self.provider.chat(
                messages=self.history,
                task_type="code"  # 强制使用 deepseek-reasoner 进行严谨推理
            )
            
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            reasoning = result.get("reasoning_content", "") if isinstance(result, dict) else ""
            
            if reasoning:
                logger.info("[Agent] 思考过程: {}", reasoning[:100].replace("\n", " ") + "...")
                
            self.history.append({"role": "assistant", "content": content})
            
            # 3. 解析指令并执行
            action_str = self._extract_action(content)
            
            # 如果 AI 没有给出任何指令，防止死循环
            if not action_str:
                action_str = "WAIT(3)"
                
            feedback = await self._execute_action(action_str)
            
            if feedback.startswith("!!DONE!!"):
                logger.info("[Agent] 任务成功结束 ✅: {}", feedback.replace("!!DONE!!", "").strip())
                return True
                
            # 将反馈作为观察到的动作结果记录，以便下一轮（此处不放进 history，由下一轮截图隐式反馈，也可显式放）
            # self.history.append({"role": "user", "content": f"系统执行反馈: {feedback}"})
            
            # 安全缓冲，允许强制中止
            await asyncio.sleep(1)
            
        logger.warning("[Agent] 达到最大操作步数限制 ({})，任务中止。", self.max_steps)
        return False
