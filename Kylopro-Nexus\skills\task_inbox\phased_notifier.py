"""
分阶段进度通知器
集成到任务收件箱，提供分阶段提示和进度报告
"""

import asyncio
import time
from datetime import datetime
from typing import Callable, Optional
from enum import Enum
import random

class TaskPhase(Enum):
    """任务阶段"""
    STARTING = "starting"      # 开始阶段
    ANALYZING = "analyzing"    # 分析阶段  
    PROCESSING = "processing"  # 处理阶段
    FINALIZING = "finalizing"  # 收尾阶段
    COMPLETING = "completing"  # 完成阶段

class PhasedNotifier:
    """分阶段通知器"""
    
    def __init__(self, send_func: Callable[[str], None], task_name: str):
        """
        初始化分阶段通知器
        
        Args:
            send_func: 发送消息的函数
            task_name: 任务名称
        """
        self.send = send_func
        self.task_name = task_name
        self.current_phase = None
        self.start_time = None
        self.subtask_count = 0
        self.completed_subtasks = 0
        
        # 阶段配置
        self.phase_configs = {
            TaskPhase.STARTING: {
                "emoji": "🚀",
                "messages": [
                    f"开始执行: {task_name}",
                    f"任务启动: {task_name}",
                    f"准备执行: {task_name}"
                ]
            },
            TaskPhase.ANALYZING: {
                "emoji": "🧠", 
                "messages": [
                    "分析需求中...",
                    "解析任务结构...",
                    "理解需求文档..."
                ]
            },
            TaskPhase.PROCESSING: {
                "emoji": "⚙️",
                "messages": [
                    "处理子任务中...",
                    "执行具体操作...",
                    "运行任务逻辑..."
                ]
            },
            TaskPhase.FINALIZING: {
                "emoji": "📝",
                "messages": [
                    "整理执行结果...",
                    "生成报告文档...",
                    "归档任务文件..."
                ]
            },
            TaskPhase.COMPLETING: {
                "emoji": "✅",
                "messages": [
                    "即将完成...",
                    "最后检查中...",
                    "准备交付结果..."
                ]
            }
        }
        
        # 进度里程碑
        self.progress_milestones = [25, 50, 75]
        self.reported_milestones = set()
    
    async def start(self):
        """开始任务"""
        self.start_time = datetime.now()
        await self.enter_phase(TaskPhase.STARTING)
        
        # 发送任务信息
        await self.send(f"""
📋 [任务信息]
━━━━━━━━━━━━━━━━━━━━
任务: {self.task_name}
开始时间: {self.start_time.strftime('%H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━
💡 我会分阶段报告进度，你可以随时询问状态
""")
    
    async def enter_phase(self, phase: TaskPhase):
        """进入新阶段"""
        self.current_phase = phase
        config = self.phase_configs[phase]
        
        # 随机选择消息
        message = random.choice(config["messages"])
        
        await self.send(f"{config['emoji']} 进入{phase.value}阶段: {message}")
    
    async def update_subtask_progress(self, completed: int, total: int, 
                                    subtask_name: Optional[str] = None):
        """更新子任务进度"""
        self.subtask_count = total
        self.completed_subtasks = completed
        
        progress = (completed / total * 100) if total > 0 else 0
        
        # 检查里程碑
        for milestone in self.progress_milestones:
            if progress >= milestone and milestone not in self.reported_milestones:
                await self.send(f"📊 进度里程碑: {milestone}% 完成")
                self.reported_milestones.add(milestone)
        
        # 每完成25%的子任务报告一次
        if completed > 0 and completed % max(1, total // 4) == 0:
            if subtask_name:
                await self.send(f"⚡ 完成子任务: {subtask_name} ({completed}/{total})")
            else:
                await self.send(f"⚡ 进度: {completed}/{total} 个子任务完成 ({progress:.0f}%)")
    
    async def send_detailed_status(self):
        """发送详细状态报告"""
        if not self.start_time:
            return
        
        elapsed = datetime.now() - self.start_time
        elapsed_seconds = elapsed.total_seconds()
        
        # 计算预计剩余时间（基于当前进度）
        if self.subtask_count > 0 and self.completed_subtasks > 0:
            avg_time_per_task = elapsed_seconds / self.completed_subtasks
            remaining_tasks = self.subtask_count - self.completed_subtasks
            estimated_remaining = avg_time_per_task * remaining_tasks
            
            # 格式化时间
            if estimated_remaining < 60:
                remaining_str = f"{estimated_remaining:.0f}秒"
            elif estimated_remaining < 3600:
                remaining_str = f"{estimated_remaining/60:.1f}分钟"
            else:
                remaining_str = f"{estimated_remaining/3600:.1f}小时"
        else:
            remaining_str = "计算中..."
        
        # 格式化已用时间
        if elapsed_seconds < 60:
            elapsed_str = f"{elapsed_seconds:.0f}秒"
        elif elapsed_seconds < 3600:
            elapsed_str = f"{elapsed_seconds/60:.1f}分钟"
        else:
            elapsed_str = f"{elapsed_seconds/3600:.1f}小时"
        
        status_report = f"""
📈 [详细状态报告]
━━━━━━━━━━━━━━━━━━━━
任务: {self.task_name}
当前阶段: {self.current_phase.value if self.current_phase else '未开始'}
子任务进度: {self.completed_subtasks}/{self.subtask_count}
━━━━━━━━━━━━━━━━━━━━
⏰ 已运行: {elapsed_str}
⏳ 预计剩余: {remaining_str}
━━━━━━━━━━━━━━━━━━━━
💡 提示: 回复'状态'查看最新进度
"""
        
        await self.send(status_report)
    
    async def complete(self, success: bool = True, result: Optional[str] = None):
        """完成任务"""
        if not self.start_time:
            return
        
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        if success:
            await self.enter_phase(TaskPhase.COMPLETING)
            
            # 格式化持续时间
            if duration < 60:
                duration_str = f"{duration:.1f}秒"
            elif duration < 3600:
                duration_str = f"{duration/60:.1f}分钟"
            else:
                duration_str = f"{duration/3600:.1f}小时"
            
            completion_message = f"""
🎉 [任务完成]
━━━━━━━━━━━━━━━━━━━━
任务: {self.task_name}
状态: ✅ 成功完成
耗时: {duration_str}
子任务: {self.completed_subtasks}/{self.subtask_count} 完成
━━━━━━━━━━━━━━━━━━━━
"""
            if result:
                completion_message += f"结果: {result[:200]}...\n"
            
            await self.send(completion_message)
        else:
            await self.send(f"❌ 任务失败: {self.task_name}\n运行时间: {duration:.1f}秒")
    
    async def send_quick_status(self):
        """发送快速状态（用于情感回应层）"""
        if not self.start_time:
            await self.send("💤 当前没有正在执行的任务")
            return
        
        progress = (self.completed_subtasks / self.subtask_count * 100) if self.subtask_count > 0 else 0
        
        quick_status = f"""
⚡ [快速状态]
任务: {self.task_name}
进度: {progress:.0f}%
子任务: {self.completed_subtasks}/{self.subtask_count}
"""
        await self.send(quick_status)

# 集成到现有 inbox.py 的辅助函数
def create_phased_notifier(inbox_instance, task_name: str) -> PhasedNotifier:
    """创建分阶段通知器"""
    async def send_message(msg: str):
        await inbox_instance._notify(msg)
    
    return PhasedNotifier(send_message, task_name)