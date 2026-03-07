#!/usr/bin/env python3
"""
测试任务调度器
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

async def test_dispatcher():
    """测试任务调度器"""
    try:
        print("1. 测试任务调度器...")
        from skills.task_inbox.dispatcher import TaskDispatcher
        
        dispatcher = TaskDispatcher(workspace=".")
        
        print("2. 创建测试任务数据...")
        task_data = {
            "title": "测试任务：IDE桥接器功能验证",
            "summary": "测试Kylopro的IDE桥接器功能",
            "subtasks": [
                {
                    "id": 1,
                    "action": "create_file",
                    "target": "test_antigravity.py",
                    "detail": "创建一个测试Antigravity的Python脚本",
                    "skill": "ide_bridge"
                },
                {
                    "id": 2,
                    "action": "run_command",
                    "target": "python --version",
                    "detail": "检查Python版本",
                    "skill": "ide_bridge"
                },
                {
                    "id": 3,
                    "action": "analyze",
                    "target": "",
                    "detail": "分析Antigravity的集成方案",
                    "skill": "provider"
                }
            ]
        }
        
        print("3. 执行任务...")
        result = await dispatcher.execute_all(task_data, task_id="test_001")
        
        print(f"4. 执行结果:")
        print(f"   标题: {result.get('title')}")
        print(f"   总计: {result.get('total')}")
        print(f"   成功: {result.get('success')}")
        print(f"   失败: {result.get('failed')}")
        
        for r in result.get('results', []):
            icon = "✅" if r['status'] == 'success' else "❌"
            print(f"   {icon} #{r['id']} {r['action']}: {r['output'][:80]}...")
        
        print("✅ 调度器测试完成！")
        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_dispatcher())