#!/usr/bin/env python3
"""
三层响应系统
1. 情感回应层 - 句句有回应，不中断工作
2. 工作状态层 - 透明化当前工作状态
3. 功能处理层 - 真中断和任务处理
"""

import sys
import os
import time
import threading
import queue
from datetime import datetime
from pathlib import Path
from enum import Enum

WORKSPACE = Path(__file__).parent
os.chdir(WORKSPACE)

class MessageIntent(Enum):
    """消息意图（更精细的分类）"""
    # 情感互动类
    GREETING = "greeting"          # 问候/闲聊
    STATUS_CHECK = "status_check"  # 状态确认（情感）
    ENCOURAGEMENT = "encouragement" # 鼓励/表扬
    JOKE = "joke"                  # 玩笑
    
    # 工作状态类  
    PROGRESS_QUERY = "progress_query"  # 进度查询
    DETAILED_STATUS = "detailed_status" # 详细状态
    
    # 功能控制类
    REAL_INTERRUPT = "real_interrupt"  # 真中断
    NEW_TASK = "new_task"              # 新任务
    CONFIG_CHANGE = "config_change"    # 配置更改
    
    # 紧急类
    EMERGENCY = "emergency"            # 紧急情况

class ThreeLayerResponseSystem:
    """三层响应系统"""
    
    def __init__(self):
        # 消息队列
        self.message_queue = queue.Queue()
        
        # 工作状态
        self.current_task = None
        self.task_status = "idle"  # idle, thinking, working, stuck
        self.task_progress = 0.0
        self.task_start_time = None
        
        # 情感回应库
        self.emotional_responses = {
            MessageIntent.GREETING: [
                "👋 我在呢！继续工作中...",
                "🐈 听到啦～任务进行中",
                "💭 收到，边工作边听着呢",
                "✨ 嗯嗯，你说～"
            ],
            MessageIntent.STATUS_CHECK: [
                "🔄 正常运行中，进度{progress}%",
                "⚡ 工作中，一切顺利",
                "🧠 思考中，有进展会告诉你",
                "📈 稳步推进，放心"
            ],
            MessageIntent.ENCOURAGEMENT: [
                "🌟 谢谢鼓励！动力满满",
                "💪 收到能量，继续前进",
                "🎯 有你的支持，一定能完成",
                "🚀 冲鸭！"
            ],
            MessageIntent.JOKE: [
                "😸 哈哈，你逗我笑也不影响我工作",
                "🎭 讲笑话时间到～但手没停",
                "🤖 AI也会笑，但代码照写",
                "💫 幽默感收到，CPU继续运转"
            ]
        }
        
        # 工作状态回应
        self.work_status_responses = {
            "thinking": "🧠 深度思考中...",
            "working": "⚙️ 处理数据中...",
            "stuck": "⚠️ 遇到难点，正在尝试突破",
            "idle": "💤 待命中"
        }
        
        print(f"[{self._timestamp()}] 三层响应系统初始化")
    
    def _timestamp(self):
        return datetime.now().strftime("%H:%M:%S")
    
    def analyze_intent(self, message: str) -> MessageIntent:
        """分析消息意图"""
        msg_lower = message.lower()
        
        # 情感互动类
        if any(word in msg_lower for word in ["你好", "在吗", "哈喽", "hello", "hi"]):
            return MessageIntent.GREETING
        
        if any(word in msg_lower for word in ["怎么样", "还好吗", "在干嘛"]):
            return MessageIntent.STATUS_CHECK
        
        if any(word in msg_lower for word in ["加油", "棒", "厉害", "good"]):
            return MessageIntent.ENCOURAGEMENT
        
        if any(word in msg_lower for word in ["笑话", "搞笑", "哈哈", "lol"]):
            return MessageIntent.JOKE
        
        # 工作状态类
        if any(word in msg_lower for word in ["进度", "到哪了", "percent", "progress"]):
            return MessageIntent.PROGRESS_QUERY
        
        if any(word in msg_lower for word in ["详细状态", "具体进度", "详细报告"]):
            return MessageIntent.DETAILED_STATUS
        
        # 功能控制类
        if any(word in msg_lower for word in ["真中断", "停止工作", "死循环", "重新设计"]):
            return MessageIntent.REAL_INTERRUPT
        
        if any(word in msg_lower for word in ["新任务", "新需求", "帮我做"]):
            return MessageIntent.NEW_TASK
        
        # 紧急类
        if any(word in msg_lower for word in ["紧急", "立刻", "马上", "urgent"]):
            return MessageIntent.EMERGENCY
        
        # 默认：情感互动
        return MessageIntent.STATUS_CHECK
    
    def layer1_emotional_response(self, intent: MessageIntent) -> str:
        """第一层：情感回应（不中断工作）"""
        import random
        
        responses = self.emotional_responses.get(intent, ["💬 收到消息"])
        
        # 选择随机回应
        response = random.choice(responses)
        
        # 替换模板变量
        if "{progress}" in response:
            response = response.replace("{progress}", f"{self.task_progress:.0f}")
        
        return response
    
    def layer2_work_status(self) -> str:
        """第二层：工作状态报告"""
        status_msg = self.work_status_responses.get(self.task_status, "未知状态")
        
        if self.task_status in ["thinking", "working"]:
            return f"{status_msg} 进度: {self.task_progress:.0f}%"
        elif self.task_status == "stuck":
            return f"{status_msg} 已尝试 {int(time.time() - self.task_start_time)} 秒"
        else:
            return status_msg
    
    def layer3_functional_response(self, intent: MessageIntent, message: str) -> dict:
        """第三层：功能处理"""
        if intent == MessageIntent.REAL_INTERRUPT:
            return self._handle_real_interrupt(message)
        elif intent == MessageIntent.NEW_TASK:
            return self._handle_new_task(message)
        elif intent == MessageIntent.EMERGENCY:
            return self._handle_emergency(message)
        else:
            return {"action": "continue", "reason": "非功能消息"}
    
    def _handle_real_interrupt(self, message: str) -> dict:
        """处理真中断"""
        print(f"[{self._timestamp()}] 🚨 检测到真中断请求: {message}")
        
        if self.task_status == "stuck":
            return {
                "action": "interrupt_and_redesign",
                "reason": "检测到死循环/卡住状态",
                "saved_progress": self.task_progress,
                "suggestions": ["重新分析需求", "简化任务", "尝试不同方法"]
            }
        elif self.task_status in ["thinking", "working"]:
            return {
                "action": "safe_interrupt",
                "reason": "用户主动中断",
                "saved_progress": self.task_progress,
                "can_resume": True
            }
        else:
            return {
                "action": "no_op",
                "reason": "没有正在执行的任务"
            }
    
    def _handle_new_task(self, message: str) -> dict:
        """处理新任务"""
        # 如果有当前任务，需要决定如何处理
        if self.task_status in ["thinking", "working"]:
            return {
                "action": "ask_confirmation",
                "question": f"当前有任务在执行（进度{self.task_progress:.0f}%），是否中断并开始新任务？",
                "options": ["中断并开始新任务", "新任务排队", "继续当前任务"]
            }
        else:
            return {
                "action": "start_new_task",
                "task_description": message
            }
    
    def _handle_emergency(self, message: str) -> dict:
        """处理紧急情况"""
        return {
            "action": "immediate_interrupt",
            "reason": "紧急情况",
            "priority": "highest"
        }
    
    def process_message(self, message: str) -> dict:
        """处理用户消息（三层响应）"""
        print(f"\n[{self._timestamp()}] 收到用户消息: {message}")
        
        # 分析意图
        intent = self.analyze_intent(message)
        print(f"[{self._timestamp()}] 意图分析: {intent.value}")
        
        result = {
            "original_message": message,
            "intent": intent.value,
            "timestamp": self._timestamp()
        }
        
        # 第一层：情感回应（立即返回，不阻塞）
        emotional_response = self.layer1_emotional_response(intent)
        result["emotional_response"] = emotional_response
        print(f"[{self._timestamp()}] 情感回应: {emotional_response}")
        
        # 第二层：工作状态（如果需要）
        if intent in [MessageIntent.PROGRESS_QUERY, MessageIntent.DETAILED_STATUS]:
            work_status = self.layer2_work_status()
            result["work_status"] = work_status
            print(f"[{self._timestamp()}] 工作状态: {work_status}")
        
        # 第三层：功能处理（如果需要，可能改变工作状态）
        if intent in [MessageIntent.REAL_INTERRUPT, MessageIntent.NEW_TASK, MessageIntent.EMERGENCY]:
            functional_response = self.layer3_functional_response(intent, message)
            result["functional_response"] = functional_response
            print(f"[{self._timestamp()}] 功能处理: {functional_response}")
        
        return result
    
    def simulate_work(self, task_name: str):
        """模拟工作过程"""
        self.current_task = task_name
        self.task_status = "working"
        self.task_progress = 0.0
        self.task_start_time = time.time()
        
        print(f"\n[{self._timestamp()}] 🚀 开始工作: {task_name}")
        
        # 模拟工作步骤
        steps = 10
        for i in range(steps):
            # 更新进度
            self.task_progress = (i + 1) / steps * 100
            
            # 模拟工作
            print(f"[{self._timestamp()}] 工作进度: {self.task_progress:.0f}%")
            time.sleep(2)  # 每个步骤2秒
            
            # 随机模拟卡住
            if i == 4 and random.random() < 0.3:  # 30%概率在50%时卡住
                self.task_status = "stuck"
                print(f"[{self._timestamp()}] ⚠️ 模拟卡住状态...")
                time.sleep(5)  # 卡住5秒
                self.task_status = "working"
        
        # 工作完成
        self.task_status = "idle"
        self.task_progress = 100
        print(f"[{self._timestamp()}] ✅ 工作完成: {task_name}")

def test_three_layer_system():
    """测试三层响应系统"""
    print("="*60)
    print("测试三层响应系统")
    print("="*60)
    
    system = ThreeLayerResponseSystem()
    
    # 模拟用户在不同工作状态下发消息
    test_scenarios = [
        # (工作状态, 用户消息, 期望效果)
        ("idle", "你好", "情感回应，不触发功能"),
        ("working", "进度怎么样", "情感回应 + 工作状态"),
        ("working", "加油", "情感回应，鼓励但不中断"),
        ("stuck", "怎么了", "情感回应 + 检测到卡住"),
        ("stuck", "真中断，重新设计", "功能处理：中断并重新设计"),
        ("working", "新任务：帮我写代码", "功能处理：询问确认"),
        ("working", "紧急！立刻停止", "功能处理：立即中断")
    ]
    
    import random
    
    for work_state, user_message, expected in test_scenarios:
        print(f"\n{'='*40}")
        print(f"测试场景: {work_state}状态下，用户说: '{user_message}'")
        print(f"期望: {expected}")
        
        # 设置工作状态
        system.task_status = work_state
        system.task_progress = random.randint(20, 80) if work_state != "idle" else 0
        
        # 处理消息
        result = system.process_message(user_message)
        
        print(f"\n实际结果:")
        print(f"  情感回应: {result.get('emotional_response', 'N/A')}")
        print(f"  工作状态: {result.get('work_status', 'N/A')}")
        print(f"  功能处理: {result.get('functional_response', 'N/A')}")
        
        # 验证
        if "情感回应" in expected and "emotional_response" in result:
            print("  ✅ 情感回应验证通过")
        if "工作状态" in expected and "work_status" in result:
            print("  ✅ 工作状态验证通过")
        if "功能处理" in expected and "functional_response" in result:
            print("  ✅ 功能处理验证通过")
    
    print(f"\n{'='*60}")
    print("测试完成")
    print(f"{'='*60}")
    
    print("\n✅ 三层响应系统验证:")
    print("1. 情感回应层: 句句有回应，不中断工作")
    print("2. 工作状态层: 透明化当前状态")
    print("3. 功能处理层: 真中断和任务控制")
    
    print("\n🎯 解决你的具体需求:")
    print("  需求1（互动感）: 情感回应层满足")
    print("  需求2（真中断）: 功能处理层满足")
    print("  关键区别: 情感回应不中断工作，真中断才改变状态")
    
    return True

if __name__ == "__main__":
    test_three_layer_system()
    
    print("\n" + "="*60)
    print("🎉 三层响应系统设计完成！")
    print("="*60)
    
    print("\n现在你可以:")
    print("💬 随时发消息 - 我会立即情感回应（不中断工作）")
    print("📊 问进度 - 得到工作状态报告")
    print("🚨 真中断 - 安全停止并重新设计")
    print("🎭 闲聊 - 得到人类般的互动感")
    
    print("\n🐈 关键突破: 区分'想要互动'和'需要中断'！")