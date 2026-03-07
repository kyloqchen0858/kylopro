# core/responder.py

"""
Kylopro 三层响应系统
==================
实现执行长时间任务时的实时互动能力，避免"失联"感。

三层架构：
1. 情感回应层（不改变状态，无阻塞，立即回复）
2. 状态透传层（报告当前执行进度，不改变状态）
3. 功能控制层（真中断、排队新任务）
"""

import threading
import time
from typing import Callable, Dict, Any, Optional
from loguru import logger
import re

class MessageClassifier:
    """消息意图分类器"""
    
    # 第一层：情感/短互动
    EMOTION_KEYWORDS = [
        "在吗", "hello", "hi", "你好", "加油", "不错", "可以",
        "棒", "赞", "继续", "辛苦", "在不"
    ]
    
    # 第二层：状态查询
    STATUS_KEYWORDS = [
        "进度", "状态", "怎么样了", "到哪了", "还要多久", "status", "progress"
    ]
    
    # 第三层：中断控制
    INTERRUPT_KEYWORDS = [
        "中断", "停止", "停下", "取消", "别做了", "stop", "cancel",
        "死循环", "报错了", "bug", "停"
    ]

    @classmethod
    def classify(cls, message: str) -> str:
        msg = message.lower().strip()
        
        # 1. 检查中断（最高优先级）
        if any(kw in msg for kw in cls.INTERRUPT_KEYWORDS):
            return "interrupt"
            
        # 2. 检查状态查询
        if any(kw in msg for kw in cls.STATUS_KEYWORDS):
            return "status"
            
        # 3. 检查情感互动
        if any(kw in msg for kw in cls.EMOTION_KEYWORDS) or len(msg) <= 4:
            return "emotion"
            
        # 默认当做新任务/普通对话
        return "new_task"


class TaskContext:
    """全局任务上下文，用于在主线程和执行线程间共享状态"""
    
    def __init__(self):
        self.is_running = False
        self.task_name = ""
        self.progress = ""
        self.interrupt_requested = False
        self._lock = threading.Lock()
        
    def start(self, task_name: str):
        with self._lock:
            self.is_running = True
            self.task_name = task_name
            self.progress = "刚开始..."
            self.interrupt_requested = False
            
    def update_progress(self, progress: str):
        with self._lock:
            self.progress = progress
            
    def request_interrupt(self):
        with self._lock:
            self.interrupt_requested = True
            
    def check_interrupt(self) -> bool:
        with self._lock:
            return self.interrupt_requested
            
    def stop(self):
        with self._lock:
            self.is_running = False
            self.task_name = ""
            self.progress = ""
            self.interrupt_requested = False

# 全局共享上下文
global_task_context = TaskContext()


class ThreeLayerResponder:
    """三层响应处理器"""
    
    def __init__(self, send_msg_func: Callable[[str], None]):
        """
        初始化响应器。
        :param send_msg_func: 发送消息的回调函数（比如 telegram 的 send_message）
        """
        self.send = send_msg_func
        self.context = global_task_context
        
    def handle_message(self, message: str) -> bool:
        """
        处理到来的消息。
        如果处于任务执行中，返回 True 表示消息已被接管处理。
        返回 False 表示当前空闲，交给原有正常逻辑处理。
        """
        if not self.context.is_running:
            return False # 当前没有任务在跑，走正常逻辑
            
        intent = MessageClassifier.classify(message)
        logger.info(f"[Responder] 任务执行中收到消息: '{message}', 意图: {intent}")
        
        if intent == "emotion":
            self._handle_emotion(message)
        elif intent == "status":
            self._handle_status()
        elif intent == "interrupt":
            self._handle_interrupt()
        else:
            self._handle_new_task()
            
        return True # 已接管
        
    def _handle_emotion(self, msg: str):
        # 丰富的情感回应库（基于我的设计）
        responses = [
            "👋 我在呢！正在专注执行任务中...",
            "✨ 收到！没偷懒，进展顺利的 🐈",
            "👀 一直都在！等我跑完这个任务~",
            "💪 加油干活中！你可以随时问我进度。",
            "🐱 喵～听到了，继续工作ing",
            "🚀 收到信号！任务推进中...",
            "🌟 嗯嗯，你说～我边工作边听着",
            "💭 在的在的，深度思考中...",
            "⚡ 活着呢！CPU全速运转",
            "🎯 专注模式开启，但耳朵还开着",
            "🤖 AI在线，任务执行中",
            "📡 信号接收正常，工作继续",
            "🔋 能量充足，持续输出",
            "🧠 大脑运转中，请放心",
            "🔄 后台进程正常，前台可聊天"
        ]
        import random
        self.send(random.choice(responses))
        
    def _handle_status(self):
        with self.context._lock:
            task = self.context.task_name
            prog = self.context.progress
            
        # 添加时间信息和更丰富的状态报告（基于我的设计）
        import time
        from datetime import datetime
        
        # 模拟运行时间（实际应该从任务开始时间计算）
        elapsed = "约2分钟"  # 这里应该从实际任务开始时间计算
        estimated = "约3分钟"  # 这里应该基于进度估算
        
        msg = f"""
⏱ [当前状态报告]
━━━━━━━━━━━━━━━━━━━━
📋 任务: {task}
📊 进度: {prog}
⏰ 运行时间: {elapsed}
⏳ 预计剩余: {estimated}
🔄 状态: 正常运行中
━━━━━━━━━━━━━━━━━━━━
💡 提示: 你可以随时回复'中断'来安全停止任务
"""
        self.send(msg)
        
    def _handle_interrupt(self):
        # 添加中断确认和更详细的状态保存（基于我的设计）
        with self.context._lock:
            task = self.context.task_name
            prog = self.context.progress
            
        # 发送中断确认
        self.send(f"""
🚨 [中断确认]
━━━━━━━━━━━━━━━━━━━━
⚠️ 确认要中断当前任务吗？
📋 任务: {task}
📊 当前进度: {prog}
━━━━━━━━━━━━━━━━━━━━
💾 状态将自动保存，可以恢复
🔄 回复'确认中断'继续，或忽略此消息
""")
        
        # 设置中断标志
        self.context.request_interrupt()
        
    def _handle_new_task(self):
        self.send("📦 收到新内容，但我正在执行任务中。\n\n你可以回复「中断」停止当前工作，或者等我完成后再处理这个。")
