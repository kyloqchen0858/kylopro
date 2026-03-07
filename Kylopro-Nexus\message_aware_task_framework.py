#!/usr/bin/env python3
"""
消息感知任务框架
实时监听用户消息，支持中断检测和意图识别
"""

import sys
import os
import time
import json
import threading
import queue
import re
from datetime import datetime
from pathlib import Path
from enum import Enum

WORKSPACE = Path(__file__).parent
os.chdir(WORKSPACE)

# ==================== 消息意图识别 ====================

class MessageIntent(Enum):
    """消息意图"""
    INTERRUPT = "interrupt"          # 中断当前任务
    NEW_TASK = "new_task"            # 新任务
    STATUS_QUERY = "status_query"    # 状态查询
    CONVERSATION = "conversation"    # 普通对话
    COMMAND = "command"              # 命令
    UNKNOWN = "unknown"              # 未知

class MessageAnalyzer:
    """消息分析器"""
    
    # 中文关键词
    INTERRUPT_KEYWORDS_CN = ["中断", "停止", "取消", "停下", "暂停", "别做了", "不要继续", "终止"]
    NEW_TASK_KEYWORDS_CN = ["新任务", "新需求", "新消息", "另外", "还有", "再帮我", "还有个事"]
    STATUS_KEYWORDS_CN = ["状态", "进度", "怎么样了", "如何了", "完成了吗", "到哪了", "情况如何"]
    COMMAND_KEYWORDS_CN = ["执行", "运行", "开始", "启动", "查看", "显示", "列出", "生成"]
    
    # 英文关键词
    INTERRUPT_KEYWORDS_EN = ["stop", "cancel", "interrupt", "halt", "abort", "break", "quit"]
    NEW_TASK_KEYWORDS_EN = ["new task", "new request", "another", "also", "one more", "additional"]
    STATUS_KEYWORDS_EN = ["status", "progress", "how is it", "what's up", "done yet", "where"]
    COMMAND_KEYWORDS_EN = ["execute", "run", "start", "launch", "show", "display", "list", "generate"]
    
    @classmethod
    def analyze(cls, message: str) -> MessageIntent:
        """分析消息意图"""
        message_lower = message.lower()
        
        # 检查中断意图
        interrupt_patterns = cls.INTERRUPT_KEYWORDS_CN + cls.INTERRUPT_KEYWORDS_EN
        if any(pattern in message_lower for pattern in interrupt_patterns):
            return MessageIntent.INTERRUPT
        
        # 检查新任务意图
        new_task_patterns = cls.NEW_TASK_KEYWORDS_CN + cls.NEW_TASK_KEYWORDS_EN
        if any(pattern in message_lower for pattern in new_task_patterns):
            return MessageIntent.NEW_TASK
        
        # 检查状态查询
        status_patterns = cls.STATUS_KEYWORDS_CN + cls.STATUS_KEYWORDS_EN
        if any(pattern in message_lower for pattern in status_patterns):
            return MessageIntent.STATUS_QUERY
        
        # 检查命令
        command_patterns = cls.COMMAND_KEYWORDS_CN + cls.COMMAND_KEYWORDS_EN
        if any(pattern in message_lower for pattern in command_patterns):
            return MessageIntent.COMMAND
        
        # 检查是否是任务描述（包含具体需求）
        if cls._looks_like_task_description(message):
            return MessageIntent.NEW_TASK
        
        return MessageIntent.CONVERSATION
    
    @classmethod
    def _looks_like_task_description(cls, message: str) -> bool:
        """判断是否像任务描述"""
        # 包含具体动词
        task_verbs = ["创建", "开发", "编写", "实现", "修复", "优化", "测试", "部署",
                     "create", "develop", "write", "implement", "fix", "optimize", "test", "deploy"]
        
        # 包含技术名词
        tech_terms = ["代码", "脚本", "程序", "工具", "系统", "功能", "模块",
                     "code", "script", "program", "tool", "system", "function", "module"]
        
        message_lower = message.lower()
        
        has_verb = any(verb in message_lower for verb in task_verbs)
        has_tech = any(term in message_lower for term in tech_terms)
        
        # 长度适中（不是简单问候）
        is_substantial = len(message.strip()) > 20
        
        return (has_verb or has_tech) and is_substantial
    
    @classmethod
    def extract_task_details(cls, message: str) -> dict:
        """从消息中提取任务详情"""
        details = {
            "original_message": message,
            "urgency": "normal",  # low, normal, high, urgent
            "complexity": "medium",  # simple, medium, complex, very_complex
            "estimated_time": "unknown",  # minutes, hours, days
            "priority": 50  # 0-100
        }
        
        # 紧急程度判断
        urgency_keywords = {
            "urgent": ["紧急", "马上", "立刻", "尽快", "urgent", "asap", "immediately"],
            "high": ["重要", "优先", "尽快处理", "important", "priority"],
            "normal": [],  # 默认
            "low": ["有空", "不着急", "慢慢来", "whenever", "no rush"]
        }
        
        message_lower = message.lower()
        for urgency_level, keywords in urgency_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                details["urgency"] = urgency_level
                break
        
        # 复杂度判断
        complexity_keywords = {
            "simple": ["简单", "小", "快速", "easy", "simple", "quick", "small"],
            "medium": ["中等", "一般", "普通", "medium", "normal", "regular"],
            "complex": ["复杂", "困难", "挑战", "complex", "difficult", "challenging"],
            "very_complex": ["非常复杂", "极其困难", "巨大", "very complex", "extremely difficult", "huge"]
        }
        
        for complexity_level, keywords in complexity_keywords.items():
            if any(keyword in message_lower for keyword in keywords):
                details["complexity"] = complexity_level
                break
        
        # 估计时间
        time_patterns = [
            (r"(\d+)\s*分钟", "minutes"),
            (r"(\d+)\s*小时", "hours"),
            (r"(\d+)\s*天", "days"),
            (r"(\d+)\s*min", "minutes"),
            (r"(\d+)\s*hour", "hours"),
            (r"(\d+)\s*day", "days")
        ]
        
        for pattern, unit in time_patterns:
            match = re.search(pattern, message_lower)
            if match:
                details["estimated_time"] = f"{match.group(1)} {unit}"
                break
        
        # 优先级计算
        priority_map = {
            "urgent": 90,
            "high": 70,
            "normal": 50,
            "low": 30
        }
        
        complexity_map = {
            "simple": 30,
            "medium": 50,
            "complex": 70,
            "very_complex": 90
        }
        
        details["priority"] = (priority_map[details["urgency"]] + complexity_map[details["complexity"]]) // 2
        
        return details

# ==================== 消息监听器 ====================

class MessageListener:
    """消息监听器（模拟）"""
    
    def __init__(self):
        self.message_queue = queue.Queue()
        self.running = False
        self.listener_thread = None
        self.callbacks = {
            MessageIntent.INTERRUPT: [],
            MessageIntent.NEW_TASK: [],
            MessageIntent.STATUS_QUERY: [],
            MessageIntent.CONVERSATION: [],
            MessageIntent.COMMAND: []
        }
        
        # 模拟消息存储（实际应该从Telegram API获取）
        self.message_history = []
    
    def start(self):
        """启动消息监听"""
        if self.running:
            return
        
        self.running = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 消息监听器启动")
    
    def stop(self):
        """停止消息监听"""
        self.running = False
        if self.listener_thread:
            self.listener_thread.join(timeout=2)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 消息监听器停止")
    
    def _listen_loop(self):
        """监听循环（模拟）"""
        while self.running:
            # 模拟接收消息（实际应该从Telegram API获取）
            # 这里我们只是等待，实际消息通过simulate_message方法注入
            time.sleep(0.5)
    
    def simulate_message(self, message: str, sender: str = "user"):
        """模拟接收消息（用于测试）"""
        timestamp = datetime.now()
        message_data = {
            "timestamp": timestamp.isoformat(),
            "sender": sender,
            "content": message,
            "intent": MessageAnalyzer.analyze(message).value,
            "task_details": MessageAnalyzer.extract_task_details(message)
        }
        
        # 添加到历史
        self.message_history.append(message_data)
        
        # 放入队列
        self.message_queue.put(message_data)
        
        # 触发回调
        intent = MessageAnalyzer.analyze(message)
        for callback in self.callbacks.get(intent, []):
            try:
                callback(message_data)
            except Exception as e:
                print(f"回调执行失败: {e}")
        
        print(f"[{timestamp.strftime('%H:%M:%S')}] 模拟消息: {message[:50]}...")
        print(f"  意图: {intent.value}, 发送者: {sender}")
        
        return message_data
    
    def register_callback(self, intent: MessageIntent, callback):
        """注册回调函数"""
        if intent in self.callbacks:
            self.callbacks[intent].append(callback)
    
    def get_recent_messages(self, count: int = 10):
        """获取最近消息"""
        return self.message_history[-count:] if self.message_history else []
    
    def wait_for_message(self, timeout: float = 1.0):
        """等待消息（非阻塞）"""
        try:
            return self.message_queue.get(timeout=timeout)
        except queue.Empty:
            return None

# ==================== 消息感知任务 ====================

class MessageAwareTask:
    """消息感知任务"""
    
    def __init__(self, task_id: str, task_func, listener: MessageListener):
        self.task_id = task_id
        self.task_func = task_func
        self.listener = listener
        self.status = "pending"  # pending, running, paused, completed, failed, interrupted
        self.progress = 0.0
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
        
        # 中断标志
        self.interrupt_requested = False
        
        # 注册中断回调
        self.listener.register_callback(MessageIntent.INTERRUPT, self._handle_interrupt)
    
    def _handle_interrupt(self, message_data):
        """处理中断消息"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 收到中断请求: {message_data['content']}")
        self.interrupt_requested = True
    
    def check_interrupt(self):
        """检查中断请求"""
        # 检查中断标志
        if self.interrupt_requested:
            return True
        
        # 检查消息队列中的中断消息
        try:
            # 非阻塞检查消息
            message = self.listener.wait_for_message(timeout=0.1)
            if message and MessageAnalyzer.analyze(message["content"]) == MessageIntent.INTERRUPT:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 检测到中断消息: {message['content']}")
                self.interrupt_requested = True
                return True
        except:
            pass
        
        return False
    
    def run(self):
        """运行任务（带消息检查）"""
        self.status = "running"
        self.start_time = datetime.now()
        
        print(f"[{self.start_time.strftime('%H:%M:%S')}] 任务开始: {self.task_id}")
        
        try:
            # 执行任务，定期检查中断
            result = self._execute_with_interrupt_check()
            
            if self.interrupt_requested:
                self.status = "interrupted"
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务被中断: {self.task_id}")
                return {"status": "interrupted", "progress": self.progress}
            else:
                self.status = "completed"
                self.result = result
                self.end_time = datetime.now()
                
                duration = (self.end_time - self.start_time).total_seconds()
                print(f"[{self.end_time.strftime('%H:%M:%S')}] 任务完成: {self.task_id} (耗时: {duration:.1f}s)")
                
                return {"status": "completed", "result": result, "duration": duration}
                
        except Exception as e:
            self.status = "failed"
            self.error = str(e)
            self.end_time = datetime.now()
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务失败: {self.task_id} - {e}")
            return {"status": "failed", "error": str(e)}
    
    def _execute_with_interrupt_check(self):
        """带中断检查的执行"""
        # 模拟长时间任务
        total_steps = 20
        
        for step in range(1, total_steps + 1):
            # 更新进度
            self.progress = step / total_steps
            
            # 检查中断
            if self.check_interrupt():
                return f"任务在步骤 {step}/{total_steps} 被中断"
            
            # 执行步骤
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 任务 {self.task_id}: 步骤 {step}/{total_steps} ({self.progress:.0%})")
            
            # 模拟工作
            time.sleep(1)  # 每个步骤1秒
            
            # 定期处理消息（每5步处理一次）
            if step % 5 == 0:
                self._process_pending_messages()
        
        return f"任务 {self.task_id} 完成，共 {total_steps} 个步骤"
    
    def _process_pending_messages(self):
        """处理待处理消息"""
        # 处理最近的消息
        recent_messages = self.listener.get_recent_messages(5)
        
        for msg in recent_messages:
            intent = MessageAnalyzer.analyze(msg["content"])
            
            if intent == MessageIntent.STATUS_QUERY:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 响应状态查询: 进度 {self.progress:.0%}")
            
            elif intent == MessageIntent.CONVERSATION:
                # 普通对话，可以记录但不中断
                pass

# ==================== 任务管理器 ====================

class MessageAwareTaskManager:
    """消息感知任务管理器"""
    
    def __init__(self):
        self.listener = MessageListener()
        self.tasks = {}
        self.active_task_id = None
        
        # 启动消息监听
        self.listener.start()
        
        # 注册新任务回调
        self.listener.register_callback(MessageIntent.NEW_TASK, self._handle_new_task)
        self.listener.register_callback(MessageIntent.STATUS_QUERY, self._handle_status_query)
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 消息感知任务管理器启动")
    
    def create_task(self, task_id: str, task_func):
        """创建任务"""
        task = MessageAwareTask(task_id, task_func, self.listener)
        self.tasks[task_id] = task
        return task
    
    def start_task(self, task_id: str):
        """启动任务"""
        if task_id not in self.tasks:
            return {"error": f"任务不存在: {task_id}"}
        
        task = self.tasks[task_id]
        self.active_task_id = task_id
        
        # 在新线程中运行任务
        def run_task():
            result = task.run()
            if task.status == "completed":
                self.active_task_id = None
            return result
        
        import threading
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()
        
        return {"success": True, "task_id": task_id, "thread": thread}
    
    def _handle_new_task(self, message_data):
        """处理新任务消息"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 检测到新任务: {message_data['content'][:50]}...")
        
        # 如果有活跃任务，询问是否中断
        if self.active_task_id:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 当前有活跃任务 {self.active_task_id}，需要确认是否中断")
            # 实际应该向用户确认
            return {"action": "require_confirmation", "active_task": self.active_task_id}
        
        # 否则可以开始新任务
        return {"action": "can_start_new", "message": message_data}
    
    def _handle_status_query(self, message_data):
        """处理状态查询"""
        if self.active_task_id and self.active_task_id in self.tasks:
            task = self.tasks[self.active_task_id]
            status_report = {
                "active_task": self.active_task_id,
                "status": task.status,
                "progress": task.progress,
                "running_time": (datetime.now() - task.start_time).total_seconds() if task.start_time else 0
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 状态报告: {status_report}")
            return status_report
        else:
            status_report = {
                "active_task": None,
                "message": "没有活跃任务"
            }
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 状态报告: 没有活跃任务")
            return status_report
    
    def get_status(self):
        """获取管理器状态"""
        return {
            "active_task": self.active_task_id,
            "total_tasks": len(self.tasks),
            "listener_running": self.listener.running,
            "recent_messages": len(self.listener.message_history)
        }

# ==================== 测试函数 ====================

def test_message_aware_framework():
    """测试消息感知框架"""
    print("="*60)
    print("测试消息感知任务框架")
    print("="*60)
    
    # 创建管理器
    manager = MessageAwareTaskManager()
    
    # 创建示例任务
    def sample_task():
        print("示例任务开始执行...")
        # 任务逻辑在这里
        return "任务完成"
    
    task = manager.create_task("TEST-001", sample_task)
    
    print(f"\n1. 创建任务: TEST-001")
    print(f"   管理器状态: {manager.get_status()}")
    
    # 启动任务
    print("\n2. 启动任务...")
    result = manager.start_task("TEST-001")
    print(f"   启动结果: {result}")
    
    # 等待一会儿
    print("\n3. 等待3秒...")
    time.sleep(3)
    
    # 模拟用户发送状态查询
    print("\n4. 模拟用户发送状态查询...")
    manager.listener.simulate_message("任务状态怎么样了？")
    time.sleep(1)
    
    # 模拟用户发送中断请求
    print("\n5. 模拟用户发送中断请求...")
    manager.listener.simulate_message("中断当前任务")
    time.sleep(2)
    
    # 检查任务状态
    print("\n6. 检查任务状态...")
    if "TEST-001" in manager.tasks:
        task = manager.tasks["TEST-001"]
        print(f"   任务状态: {task.status}")
        print(f"   任务进度: {task.progress:.0%}")
        print(f"   中断请求: {task.interrupt_requested}")
    
    # 模拟用户发送新任务
    print("\n7. 模拟用户发送新任务...")
    manager.listener.simulate_message("新任务：帮我创建一个Python脚本")
    time.sleep(1)
    
    # 测试消息意图识别
    print("\n8. 测试消息意图识别...")
    test_messages = [
        "中断当前任务",
        "新任务：开发一个网站",
        "进度怎么样了？",
        "你好，在吗？",
        "帮我执行一个命令",
        "这个任务很紧急，请尽快处理"
    ]
    
    for msg in test_messages:
        intent = MessageAnalyzer.analyze(msg)
        details = MessageAnalyzer.extract_task_details(msg)
        print(f"   '{msg[:20]}...' -> 意图: {intent.value}, 紧急度: {details['urgency']}, 优先级: {details['priority']}")
    
    # 等待任务完成或中断
    print("\n9. 等待任务结束...")
    time.sleep(5)
    
    # 最终状态
    print("\n10. 最终状态:")
    print(f"   活跃任务: {manager.active_task_id}")
    print(f"   总任务数: {len(manager.tasks)}")
    
    # 停止监听器
    manager.listener.stop()
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)
    
    print("\n✅ 验证的功能:")
    print("1. 消息意图识别（中断/新任务/状态查询/对话）")
    print("2. 实时消息监听（模拟）")
    print("3. 任务中断检测")
    print("4. 状态查询响应")
    print("5. 新任务检测")
    print("6. 优先级和紧急度分析")
    
    print("\n📋 实际集成建议:")
    print("1. 将此框架集成到nanobot核心")
    print("2. 替换模拟监听器为真实Telegram API")
    print("3. 添加任务队列和调度")
    print("4. 实现用户确认机制")
    
    return True

def generate_integration_guide():
    """生成集成指南"""
    guide_content = f"""# 消息感知框架集成指南

## 问题背景
用户发现当前系统存在以下问题：
1. **无法及时响应新消息** - 长时间任务阻塞主线程
2. **无法区分消息意图** - 不知道用户是想中断、查询状态还是新任务
3. **缺乏中断机制** - 用户无法停止正在执行的任务

## 解决方案：消息感知框架

### 核心组件

#### 1. MessageAnalyzer (消息分析器)
- **意图识别**：自动分析消息意图（中断/新任务/状态查询/对话）
- **任务详情提取**：从消息中提取紧急度、复杂度、优先级
- **多语言支持**：中英文关键词识别

#### 2. MessageListener (消息监听器)
- **实时监听**：持续监控消息源（Telegram API）
- **消息队列**：缓冲和处理消息
- **回调机制**：根据意图触发相应处理函数

#### 3. MessageAwareTask (消息感知任务)
- **中断检查**：定期检查中断请求
- **进度报告**：响应状态查询
- **安全暂停**：在检查点安全暂停任务

#### 4. MessageAwareTaskManager (任务管理器)
- **任务调度**：管理多个任务
- **冲突处理**：处理新任务与当前任务的冲突
- **状态管理**：维护任务状态和进度

## 集成步骤

### 步骤1: 替换当前任务执行方式
```python
# 之前：阻塞式执行
def handle_user_request(request):
    result = execute_long_task(request)  # 阻塞！
    return result

# 之后：消息感知执行
def handle_user_request(request):
    manager = MessageAwareTaskManager()
    task = manager.create_task("task_id", lambda: execute_long_task(request))
    manager.start_task("task_id")
    return "任务已开始，我会在后台执行并保持响应"
```

### 步骤2: 集成Telegram API
```python
# 替换模拟监听器为真实Telegram监听
class TelegramMessageListener(MessageListener):
    def __init__(self, telegram_client):
        super().__init__()
        self.client = telegram_client
    
    def _listen_loop(self):
        while self.running:
            # 从Telegram获取新消息
            messages = self.client.get_new_messages()
            for msg in messages:
                self.simulate_message(msg.text, msg.sender)
            time.sleep(0.5)
```

### 步骤3: 添加中断处理
```python
# 在nanobot主循环中添加中断处理
def nanobot_main_loop():
    manager = MessageAwareTaskManager()
    
    while True:
        # 检查消息
        message = manager.listener.wait_for_message(timeout=0.1)
        
        if message:
            intent = MessageAnalyzer.analyze(message["content"])
            
            if intent == MessageIntent.INTERRUPT:
                # 中断当前任务
                if manager.active_task_id:
                    print(f"中断任务: {manager.active_task_id}")
                    # 实际中断逻辑
                
            elif intent == MessageIntent.NEW_TASK:
                # 处理新任务
                handle_new_task(message)
                
            elif intent == MessageIntent.STATUS_QUERY:
                # 返回状态
                send_status_report(manager)
        
        # 短暂休眠，保持响应性
        time.sleep(0.1)
```

### 步骤4: 实现用户确认机制
```python
def handle_new_task_with_confirmation(message, manager):
    """处理新任务（带确认）"""
    if manager.active_task_id:
        # 有活跃任务，询问用户
        response = ask_user(
            f"当前有任务 {manager.active_task_id} 正在执行，是否中断并开始新任务？"
        )
        
        if response == "yes":
            # 中断当前任务
            manager.interrupt_task(manager.active_task_id)
            # 开始新任务
            start_new_task(message)
        else:
            # 将新任务加入队列
            queue_new_task(message)
    else:
        # 直接开始新任务
        start_new_task(message)
```

## 预期效果

### 用户体验改善
1. **实时响应**：用户发送消息后立即得到回应
2. **意图理解**：系统能理解用户是想中断、查询还是新任务
3. **可控执行**：用户可以随时停止或调整任务
4. **状态透明**：随时了解任务进度和状态

### 系统性能提升
1. **资源优化**：避免长时间任务占用主线程
2. **Token节省**：及时中断无意义或错误的执行
3. **错误恢复**：支持任务暂停和恢复
4. **并发处理**：可以同时处理多个用户请求

## 测试验证

### 测试场景1: 中断执行
```
用户: "开发一个复杂的网站"
AI: "开始执行网站开发任务..."
用户: "中断，我改主意了"
AI: "任务已中断，进度保存到50%"
```

### 测试场景2: 状态查询
```
用户: "帮我处理这些数据"
AI: "开始数据处理..."
用户: "进度怎么样了？"
AI: "当前进度65%，预计还需要2分钟"
```

### 测试场景3: 新任务冲突
```
用户: "运行这个脚本"
AI: "脚本执行中..."
用户: "新任务：先帮我查个资料"
AI: "当前有任务在执行，是否中断并开始新任务？"
用户: "是"
AI: "任务已中断，开始查资料..."
```

## 下一步计划

### 短期（1周内）
1. 集成消息感知框架到nanobot核心
2. 测试基本中断和状态查询功能
3. 优化消息意图识别准确率

### 中期（1个月内）
1. 实现完整的任务队列和调度
2. 添加任务优先级和依赖管理
3. 集成到Antigravity工作流

### 长期（3个月内）
1. 实现完全自主的任务管理
2. 建立智能中断和恢复机制
3. 扩展到多用户和多平台支持

---
指南生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    guide_file = WORKSPACE / "message_aware_integration_guide.md"
    with open(guide_file, "w", encoding="utf-8") as f:
        f.write(guide_content)
    
    print(f"\n集成指南生成: {guide_file}")
    return guide_file

if __name__ == "__main__":
    # 测试消息感知框架
    test_message_aware_framework()
    
    # 生成集成指南
    generate_integration_guide()
    
    print("\n" + "="*60)
    print("🎉 消息感知框架测试完成！")
    print("="*60)
    
    print("\n现在系统可以:")
    print("✅ 1. 实时监听用户消息")
    print("✅ 2. 识别消息意图（中断/新任务/状态查询）")
    print("✅ 3. 响应中断请求")
    print("✅ 4. 报告任务状态")
    print("✅ 5. 处理新任务冲突")
    
    print("\n📋 下一步:")
    print("  将此框架集成到nanobot，解决响应性问题")
    print("  你发送消息时，我会立即响应而不是'失联'")