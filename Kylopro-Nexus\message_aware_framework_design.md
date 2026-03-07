# 消息感知框架 - 详细设计规范

## 设计目标
解决用户发现的响应性问题：
1. **无法及时响应新消息** - 长时间任务阻塞主线程
2. **无法区分消息意图** - 不知道用户是想中断、查询状态还是新任务
3. **缺乏中断机制** - 用户无法停止正在执行的任务

## 系统架构

### 整体架构图
```
用户消息 → Telegram API → 消息监听器 → 消息分析器 → 意图识别
    ↓                                        ↓
任务管理器 ← 中断处理器 ← 意图路由器 ← 任务详情提取
    ↓
任务执行器 → 状态监控器 → 进度报告
```

### 组件职责

#### 1. MessageListener (消息监听器)
- **职责**: 实时监听Telegram消息
- **输入**: Telegram API消息流
- **输出**: 标准化消息对象
- **特性**: 非阻塞，异步，支持重连

#### 2. MessageAnalyzer (消息分析器)
- **职责**: 分析消息意图和提取任务详情
- **输入**: 原始消息文本
- **输出**: 意图分类 + 任务详情
- **特性**: 多语言支持，上下文感知，置信度评分

#### 3. IntentRouter (意图路由器)
- **职责**: 根据意图路由到相应处理器
- **输入**: 意图 + 任务详情
- **输出**: 处理指令
- **特性**: 优先级管理，冲突检测，队列管理

#### 4. InterruptHandler (中断处理器)
- **职责**: 处理中断请求，安全暂停任务
- **输入**: 中断指令 + 当前任务状态
- **输出**: 中断结果 + 保存的状态
- **特性**: 安全检查点，状态保存，可恢复性

#### 5. TaskManager (任务管理器)
- **职责**: 管理任务生命周期和调度
- **输入**: 任务指令
- **输出**: 任务状态和结果
- **特性**: 并发控制，资源管理，错误恢复

#### 6. StatusMonitor (状态监控器)
- **职责**: 监控任务状态，生成进度报告
- **输入**: 任务状态数据
- **输出**: 状态报告和通知
- **特性**: 实时更新，预估时间，异常检测

## 详细设计

### 1. 消息意图识别系统

#### 意图分类
```python
class MessageIntent(Enum):
    # 核心意图
    INTERRUPT = "interrupt"          # 中断当前任务
    NEW_TASK = "new_task"            # 新任务请求
    STATUS_QUERY = "status_query"    # 状态查询
    CONVERSATION = "conversation"    # 普通对话
    
    # 扩展意图
    COMMAND = "command"              # 系统命令
    CONFIGURATION = "configuration"  # 配置更改
    FEEDBACK = "feedback"            # 反馈和建议
    EMERGENCY = "emergency"          # 紧急情况
```

#### 识别算法
采用**多级识别策略**：
1. **关键词匹配** (第一级，快速)
2. **模式识别** (第二级，中等复杂度)
3. **AI模型分析** (第三级，高准确率，可选)

```python
def analyze_intent(message: str, context: dict) -> IntentResult:
    # 第一级：关键词匹配
    intent = keyword_match(message)
    if intent.confidence > 0.8:
        return intent
    
    # 第二级：模式识别
    intent = pattern_match(message, context)
    if intent.confidence > 0.7:
        return intent
    
    # 第三级：AI模型分析（如果启用）
    if AI_MODEL_ENABLED:
        intent = ai_analyze(message, context)
        return intent
    
    # 默认：普通对话
    return IntentResult(
        intent=MessageIntent.CONVERSATION,
        confidence=0.5,
        details={"reason": "未识别到特定意图"}
    )
```

#### 关键词库设计
```python
INTENT_KEYWORDS = {
    MessageIntent.INTERRUPT: {
        "cn": ["中断", "停止", "取消", "停下", "暂停", "别做了", "不要继续", "终止", "算了"],
        "en": ["stop", "cancel", "interrupt", "halt", "abort", "break", "quit", "cease"],
        "patterns": [
            r"^(别|不要|停止).*(了|吧|啊)",
            r".*(中断|取消|停止).*任务",
            r"stop.*now|cancel.*immediately"
        ]
    },
    
    MessageIntent.NEW_TASK: {
        "cn": ["新任务", "新需求", "新消息", "另外", "还有", "再帮我", "还有个事", "帮我"],
        "en": ["new task", "new request", "another", "also", "one more", "additional", "help me"],
        "patterns": [
            r"^(帮我|请帮我|麻烦).*",
            r".*(开发|创建|编写|实现|修复|优化|测试|部署).*",
            r"can you.*|please.*for me"
        ]
    },
    
    MessageIntent.STATUS_QUERY: {
        "cn": ["状态", "进度", "怎么样了", "如何了", "完成了吗", "到哪了", "情况如何", "进行得"],
        "en": ["status", "progress", "how is it", "what's up", "done yet", "where", "how's going"],
        "patterns": [
            r".*(怎么样|如何|了吗|没)$",
            r"what.*status|how.*progress",
            r".*完成.*了.*没"
        ]
    }
}
```

### 2. 中断处理系统

#### 中断流程
```
用户发送中断 → 意图识别 → 中断确认 → 安全检查点 → 状态保存 → 任务暂停 → 用户确认
```

#### 安全检查点机制
```python
class SafeCheckpoint:
    """安全检查点"""
    
    def __init__(self):
        self.checkpoints = []
        self.min_interval = 5  # 最小检查间隔（秒）
        self.last_checkpoint = None
    
    def can_checkpoint(self) -> bool:
        """是否可以创建检查点"""
        if not self.last_checkpoint:
            return True
        
        elapsed = time.time() - self.last_checkpoint
        return elapsed >= self.min_interval
    
    def create_checkpoint(self, task_state: dict) -> Checkpoint:
        """创建检查点"""
        checkpoint = {
            "id": f"CP_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "task_state": task_state,
            "progress": task_state.get("progress", 0),
            "memory_usage": get_memory_usage(),
            "disk_usage": get_disk_usage()
        }
        
        self.checkpoints.append(checkpoint)
        self.last_checkpoint = time.time()
        
        return checkpoint
    
    def get_latest_checkpoint(self) -> Optional[Checkpoint]:
        """获取最新检查点"""
        return self.checkpoints[-1] if self.checkpoints else None
```

#### 状态保存和恢复
```python
class TaskStateManager:
    """任务状态管理器"""
    
    def save_state(self, task_id: str, state: dict):
        """保存任务状态"""
        state_file = self._get_state_file(task_id)
        
        state_data = {
            "task_id": task_id,
            "state": state,
            "saved_at": datetime.now().isoformat(),
            "checkpoint_id": state.get("checkpoint_id"),
            "can_resume": self._can_resume(state)
        }
        
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f, ensure_ascii=False, indent=2)
        
        # 备份到云存储（可选）
        if CLOUD_BACKUP_ENABLED:
            self._backup_to_cloud(state_data)
    
    def load_state(self, task_id: str) -> Optional[dict]:
        """加载任务状态"""
        state_file = self._get_state_file(task_id)
        
        if not os.path.exists(state_file):
            return None
        
        with open(state_file, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        
        return state_data
    
    def can_resume(self, task_id: str) -> bool:
        """判断任务是否可以恢复"""
        state_data = self.load_state(task_id)
        if not state_data:
            return False
        
        return state_data.get("can_resume", False)
    
    def _can_resume(self, state: dict) -> bool:
        """判断状态是否可以恢复"""
        # 检查状态完整性
        required_fields = ["progress", "checkpoint_id", "task_type"]
        for field in required_fields:
            if field not in state:
                return False
        
        # 检查资源可用性
        if state.get("requires_gpu", False) and not GPU_AVAILABLE:
            return False
        
        return True
```

### 3. 任务调度系统

#### 任务优先级模型
```python
class TaskPriority:
    """任务优先级计算"""
    
    @staticmethod
    def calculate_priority(task_details: dict) -> int:
        """计算任务优先级（0-100）"""
        base_score = 50
        
        # 紧急度权重（40%）
        urgency_scores = {
            "emergency": 100,
            "urgent": 80,
            "high": 60,
            "normal": 40,
            "low": 20
        }
        urgency = task_details.get("urgency", "normal")
        base_score += (urgency_scores.get(urgency, 40) - 50) * 0.4
        
        # 复杂度权重（30%）
        complexity_scores = {
            "very_complex": 90,
            "complex": 70,
            "medium": 50,
            "simple": 30,
            "trivial": 10
        }
        complexity = task_details.get("complexity", "medium")
        base_score += (complexity_scores.get(complexity, 50) - 50) * 0.3
        
        # 用户价值权重（20%）
        user_value = task_details.get("user_value", 50)  # 0-100
        base_score += (user_value - 50) * 0.2
        
        # 资源需求权重（10%）
        resource_demand = task_details.get("resource_demand", 50)  # 0-100
        base_score -= (resource_demand - 50) * 0.1  # 资源需求高，优先级降低
        
        return max(0, min(100, int(base_score)))
    
    @staticmethod
    def get_priority_label(score: int) -> str:
        """获取优先级标签"""
        if score >= 90:
            return "最高"
        elif score >= 75:
            return "高"
        elif score >= 60:
            return "中高"
        elif score >= 40:
            return "中"
        elif score >= 25:
            return "中低"
        else:
            return "低"
```

#### 任务冲突处理
```python
class TaskConflictResolver:
    """任务冲突解决器"""
    
    def resolve_conflict(self, current_task: Task, new_task: Task) -> ConflictResolution:
        """解决任务冲突"""
        
        # 计算两个任务的优先级
        current_priority = TaskPriority.calculate_priority(current_task.details)
        new_priority = TaskPriority.calculate_priority(new_task.details)
        
        # 优先级差异
        priority_diff = new_priority - current_priority
        
        # 决策矩阵
        if priority_diff >= 30:
            # 新任务优先级高很多，建议中断当前任务
            return ConflictResolution(
                action="interrupt_current",
                reason=f"新任务优先级({new_priority})远高于当前任务({current_priority})",
                confidence=0.9
            )
        
        elif priority_diff >= 15:
            # 新任务优先级较高，建议询问用户
            return ConflictResolution(
                action="ask_user",
                reason=f"新任务优先级({new_priority})高于当前任务({current_priority})",
                question="是否中断当前任务并开始新任务？",
                confidence=0.7
            )
        
        elif priority_diff <= -30:
            # 当前任务优先级高很多，建议排队新任务
            return ConflictResolution(
                action="queue_new",
                reason=f"当前任务优先级({current_priority})远高于新任务({new_priority})",
                confidence=0.9
            )
        
        else:
            # 优先级相近，基于其他因素决策
            return self._resolve_by_other_factors(current_task, new_task)
    
    def _resolve_by_other_factors(self, current_task: Task, new_task: Task) -> ConflictResolution:
        """基于其他因素解决冲突"""
        factors = []
        
        # 1. 进度因素（已完成越多，越不应该中断）
        current_progress = current_task.progress
        if current_progress > 0.8:
            factors.append(("高进度", -0.3))  # 负权重，不倾向中断
        
        # 2. 时间因素（已运行时间越长，越不应该中断）
        current_duration = current_task.duration
        if current_duration > 300:  # 运行超过5分钟
            factors.append(("长时间运行", -0.2))
        
        # 3. 紧急度因素
        if new_task.details.get("urgency") == "emergency":
            factors.append(("新任务紧急", 0.4))
        
        if current_task.details.get("urgency") == "emergency":
            factors.append(("当前任务紧急", -0.4))
        
        # 4. 用户历史偏好
        user_preference = self._get_user_preference()
        if user_preference == "finish_current":
            factors.append(("用户偏好完成当前", -0.2))
        elif user_preference == "respond_immediately":
            factors.append(("用户偏好立即响应", 0.2))
        
        # 计算综合得分
        total_score = sum(weight for _, weight in factors)
        
        if total_score >= 0.3:
            return ConflictResolution(
                action="interrupt_current",
                reason="基于多因素分析，建议中断当前任务",
                confidence=0.6 + min(0.3, total_score)
            )
        elif total_score <= -0.3:
            return ConflictResolution(
                action="queue_new",
                reason="基于多因素分析，建议新任务排队",
                confidence=0.6 + min(0.3, -total_score)
            )
        else:
            return ConflictResolution(
                action="ask_user",
                reason="因素平衡，需要用户决策",
                question="当前任务和新任务优先级相近，如何处理？",
                options=["中断当前任务", "新任务排队", "并行执行（如果支持）"],
                confidence=0.5
            )
```

### 4. 状态报告系统

#### 状态报告格式
```python
class StatusReport:
    """状态报告生成器"""
    
    def generate_report(self, task: Task) -> dict:
        """生成状态报告"""
        report = {
            "task_id": task.id,
            "task_name": task.name,
            "status": task.status.value,
            "progress": task.progress,
            "start_time": task.start_time.isoformat() if task.start_time else None,
            "current_time": datetime.now().isoformat(),
            
            # 时间信息
            "elapsed_time": self._format_duration(task.elapsed_time),
            "estimated_remaining": self._estimate_remaining(task),
            "estimated_completion": self._estimate_completion_time(task),
            
            # 资源使用
            "resource_usage": {
                "cpu": get_cpu_usage(),
                "memory": get_memory_usage(),
                "disk": get_disk_usage()
            },
            
            # 详细状态
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "step_description": task.step_description,
            
            # 错误信息（如果有）
            "errors": task.errors,
            "warnings": task.warnings,
            
            # 可操作性
            "can_interrupt": task.can_interrupt,
            "can_pause": task.can_pause,
            "can_resume": task.can_resume if task.status == TaskStatus.PAUSED else False,
            
            # 建议操作
            "suggested_actions": self._suggest_actions(task)
        }
        
        return report
    
    def _estimate_remaining(self, task: Task) -> str:
        """估计剩余时间"""
        if task.progress <= 0 or not task.start_time:
            return "未知"
        
        elapsed = task.elapsed_time
        if elapsed <= 0:
            return "未知"
        
        # 简单线性估计
        estimated_total = elapsed / task.progress
        remaining = estimated_total - elapsed
        
        return self._format_duration(remaining)
    
    def _suggest_actions(self, task: Task) -> list:
        """建议操作"""
        actions = []
        
        if task.can_interrupt:
            actions.append({
                "action": "interrupt",
                "label": "中断任务",
                "description": "安全停止当前任务",
                "command": "/interrupt"
            })
        
        if task.can_pause and task.status == TaskStatus.RUNNING:
            actions.append({
                "action": "pause",
                "label": "暂停任务",
                "description": "暂停任务，稍后恢复",
                "command": "/pause"
            })
        
        if task.status == TaskStatus.PAUSED:
            actions.append({
                "action": "resume",
                "label": "恢复任务",
                "description": "从暂停点恢复任务",
                "command": "/resume"
            })
        
        actions.append({
            "action": "status",
            "label": "刷新状态",
            "description": "获取最新状态",
            "command": "/status"
        })
        
        return actions
```

## 集成方案

### 与nanobot集成
```python
# nanobot_main.py 修改方案

class EnhancedNanobot:
    """增强版nanobot"""
    
    def __init__(self):
        # 原有组件
        self.skills = load_skills()
        self.memory = MemorySystem()
        
        # 新增组件
        self.message_listener = MessageListener()
        self.message_analyzer = MessageAnalyzer()
        self.task_manager = TaskManager()
        self.status_monitor = StatusMonitor()
        
        # 启动消息监听
        self.message_listener.start()
        
        # 注册处理器
        self._register_handlers()
    
    def _register_handlers(self):
        """注册消息处理器"""
        self.message_listener.register_handler(
            MessageIntent.INTERRUPT,
            self._handle_interrupt
        )
        
        self.message_listener.register_handler(
            MessageIntent.NEW_TASK,
            self._handle_new_task
        )
        
        self.message_listener.register_handler(
            MessageIntent.STATUS_QUERY,
            self._handle_status_query
        )
    
    def main_loop(self):
        """主循环（非阻塞）"""
        while True:
            # 检查新消息（非阻塞）
            message = self.message_listener.get_message(timeout=0.1)
            
            if message:
                # 处理消息（异步）
                self._process_message_async(message)
            
            # 检查任务状态
            self.status_monitor.check_tasks()
            
            # 短暂休眠，保持响应性
            time.sleep(0.05)  # 50ms
            
    def _process_message_async(self, message):
        """异步处理消息"""
        # 在新线程中处理，避免阻塞主循环
        thread = threading.Thread(
            target=self._process_message,
            args=(message,),
            daemon=True
        )
        thread.start()
    
    def _process_message(self, message):
        """处理消息"""
        # 分析意图
        intent_result = self.message_analyzer.analyze(message)
        
        # 根据意图处理
        if intent_result.intent == MessageIntent.INTERRUPT:
            self._handle_interrupt(message, intent_result)
        
        elif intent_result.intent == MessageIntent.NEW_TASK:
            self._handle_new_task(message, intent_result)
        
        elif intent_result.intent == MessageIntent.STATUS_QUERY:
            self._handle_status_query(message, intent_result)
        
        else:
            # 普通对话，使用原有逻辑
            self._handle_conversation(message)
```

### 与现有技能集成
```python
# 修改技能执行方式

class EnhancedSkillExecutor:
    """增强版技能执行器"""
    
    def execute_skill(self, skill_name: str, params: dict) -> SkillResult:
        """执行技能（支持中断）"""
        
        # 创建可中断任务
        task = InterruptibleTask(
            task_id=f"skill_{skill_name}_{int(time.time())}",
            task_func=lambda: self._execute_skill_internal(skill_name, params),
            checkpoints=[],
            can_interrupt=True
        )
        
        # 提交到任务管理器
        self.task_manager.submit_task(task)
        
        # 立即返回，不阻塞
        return SkillResult(
            success=True,
            message=f"技能 '{skill_name}' 已开始执行",
            task_id=task.id,
            can_track=True
        )
    
    def _execute_skill_internal(self, skill_name: str, params: dict):
        """内部执行技能（可中断）"""
        skill = self.skills.get(skill_name)
        if not skill:
            raise SkillNotFoundError(skill_name)
        
        # 设置检查点回调
        skill.set_checkpoint_callback(self._create_checkpoint)
        
        # 执行技能
        try:
            result = skill.execute(params)
            return result
        except InterruptedException:
            # 正常中断
            return SkillResult(
                success=False,
                message="技能执行被中断",
                interrupted=True,
                can_resume=True
            )
```

## 测试计划

### 单元测试
1. **消息意图识别测试**
   - 测试各种中断消息的识别
   - 测试新任务消息的识别
   - 测试状态查询消息的识别
   - 测试混合意图的识别

2. **中断处理测试**
   - 测试安全检查点创建
   - 测试状态保存和恢复
   - 测试中断后的资源清理
   - 测试恢复后的状态一致性

3. **任务调度测试**
   - 测试优先级计算
   - 测试冲突解决逻辑
   - 测试队列管理
   - 测试并发控制

### 集成测试
1. **端到端测试场景**
   ```
   场景1: 正常中断
   用户: "执行长时间任务"
   AI: "开始执行..."
   用户: "中断"
   AI: "任务已中断，进度保存"
   
   场景2: 状态查询
   用户: "运行脚本"
   AI: "脚本执行中..."
   用户: "进度？"
   AI: "当前进度65%，预计剩余2分钟"
   
   场景3: 任务冲突
   用户: "处理数据"
   AI: "数据处理中..."
   用户: "新任务：紧急修复"
   AI: "当前任务进度40%，新任务紧急，是否中断？"
   用户: "是"
   AI: "任务已中断，开始紧急修复"
   ```

2. **性能测试**
   - 消息处理延迟测试
   - 并发任务处理测试
   - 内存和CPU使用测试
   - 长时间运行稳定性测试

### 用户验收测试
1. **响应性测试**
   - 用户发送消息后响应时间
   - 中断请求处理时间
   - 状态查询响应时间

2. **准确性测试**
   - 意图识别准确率
   - 状态报告准确性
   - 进度估计准确性

3. **用户体验测试**
   - 中断流程的顺畅度
   - 状态信息的清晰度
   - 错误处理的友好度

## 部署计划

### 阶段1: 原型部署（1周）
1. 集成消息监听基础框架
2. 实现基本意图识别
3. 测试简单中断场景

### 阶段2: 功能完善（2周）
1. 完善中断处理机制
2. 实现状态报告系统
3. 添加任务调度功能

### 阶段3: 优化稳定（1周）
1. 性能优化
2. 错误处理完善
3. 用户体验优化

### 阶段4: 全面部署（持续）
1. 监控和日志系统
2. 自动更新机制
3. 用户反馈收集

## 风险评估和缓解

### 风险1: 意图识别错误
- **风险**: 错误识别用户意图，导致错误操作
- **缓解**: 
  - 多级识别策略，提高准确率
  - 用户确认机制，高风险操作需要确认
  - 学习用户习惯，个性化识别

### 风险2: 中断导致数据丢失
- **风险**: 中断时未保存状态，导致数据丢失
- **缓解**:
  - 安全检查点机制，定期保存状态
  - 状态验证，恢复时检查完整性
  - 备份机制，重要数据多重备份

### 风险3: 系统资源耗尽
- **风险**: 过多并发任务导致系统资源耗尽
- **缓解**:
  - 资源限制，限制并发任务数
  - 优先级调度，优先处理重要任务
  - 监控告警，资源使用超过阈值时告警

### 风险4: 用户依赖过度
- **风险**: 用户过度依赖中断功能，频繁中断
- **缓解**:
  - 中断次数限制
  - 中断原因分析，提供优化建议
  - 教育用户合理使用

## 成功指标

### 技术指标
1. **响应时间**: 用户消息到首次响应 < 1秒
2. **意图识别准确率**: > 90%
3. **中断成功率**: > 95%
4. **状态恢复成功率**: > 90%

### 用户体验指标
1. **用户满意度**: 通过调查问卷收集
2. **中断流程评分**: 用户对中断流程的评分
3. **状态报告有用性**: 用户认为状态报告有帮助的比例

### 业务指标
1. **任务完成率**: 中断后任务仍能完成的比例
2. **资源使用效率**: 中断减少的资源浪费
3. **用户留存率**: 使用中断功能后继续使用的用户比例

## 总结

消息感知框架是解决nanobot响应性问题的关键系统。通过：
1. **实时消息监听** - 不阻塞主线程
2. **智能意图识别** - 准确理解用户意图
3. **安全中断处理** - 优雅处理中断请求
4. **透明状态报告** - 让用户了解任务状态

实现**用户随时可以中断、查询、调整任务**，同时**系统保持高效稳定运行**的目标。

这个设计为后续的**互联网分身系统**打下坚实基础，使AI能够真正作为用户的代理，在互联网世界自主行动。

---
设计完成时间: 2026-03-06 19:45
设计者: nanobot 🐈
审核者: 人类 (qianchen)