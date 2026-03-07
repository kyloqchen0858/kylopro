#!/usr/bin/env python3
"""
测试集成后的三层响应系统和分阶段提示系统
"""

import sys
import os
import asyncio
from pathlib import Path

WORKSPACE = Path(__file__).parent
os.chdir(WORKSPACE)

# 添加项目路径
sys.path.insert(0, str(WORKSPACE))

async def test_responder_system():
    """测试三层响应系统"""
    print("="*60)
    print("测试三层响应系统")
    print("="*60)
    
    from core.responder import ThreeLayerResponder, global_task_context
    
    # 模拟发送函数
    messages_sent = []
    async def mock_send(msg):
        messages_sent.append(msg)
        print(f"[模拟发送] {msg}")
    
    # 创建响应器
    responder = ThreeLayerResponder(mock_send)
    
    # 模拟任务正在执行
    global_task_context.start("测试任务")
    global_task_context.update_progress("45% - 处理数据中")
    
    print("\n1. 测试情感回应（不中断工作）:")
    test_messages = ["在吗", "hello", "加油", "辛苦啦"]
    for msg in test_messages:
        print(f"\n用户: '{msg}'")
        handled = responder.handle_message(msg)
        print(f"  是否接管: {handled}")
        print(f"  回应: {messages_sent[-1] if messages_sent else '无'}")
    
    print("\n2. 测试状态查询:")
    handled = responder.handle_message("进度怎么样了？")
    print(f"用户: '进度怎么样了？'")
    print(f"是否接管: {handled}")
    print(f"回应: {messages_sent[-1] if messages_sent else '无'}")
    
    print("\n3. 测试中断:")
    handled = responder.handle_message("中断任务")
    print(f"用户: '中断任务'")
    print(f"是否接管: {handled}")
    print(f"回应: {messages_sent[-1] if messages_sent else '无'}")
    print(f"中断标志: {global_task_context.check_interrupt()}")
    
    # 清理
    global_task_context.stop()
    
    return len(messages_sent) > 0

async def test_phased_notifier():
    """测试分阶段通知器"""
    print("\n" + "="*60)
    print("测试分阶段通知系统")
    print("="*60)
    
    from skills.task_inbox.phased_notifier import PhasedNotifier
    
    messages_sent = []
    async def mock_send(msg):
        messages_sent.append(msg)
        print(f"[通知] {msg[:80]}...")
    
    notifier = PhasedNotifier(mock_send, "集成测试任务")
    
    print("\n1. 开始任务:")
    await notifier.start()
    
    print("\n2. 进入分析阶段:")
    await notifier.enter_phase(PhasedNotifier.TaskPhase.ANALYZING)
    
    print("\n3. 更新进度:")
    await notifier.update_subtask_progress(2, 8, "数据预处理")
    await notifier.update_subtask_progress(4, 8, "模型训练")
    
    print("\n4. 详细状态报告:")
    await notifier.send_detailed_status()
    
    print("\n5. 快速状态:")
    await notifier.send_quick_status()
    
    print("\n6. 完成任务:")
    await notifier.complete(success=True, result="测试通过，所有功能正常")
    
    return len(messages_sent) >= 5

async def test_inbox_integration():
    """测试收件箱集成"""
    print("\n" + "="*60)
    print("测试任务收件箱集成")
    print("="*60)
    
    # 创建一个测试需求文件
    test_md = WORKSPACE / "data" / "inbox" / "test_integration.md"
    test_md.parent.mkdir(parents=True, exist_ok=True)
    
    test_content = """# 集成测试任务

测试三层响应系统和分阶段提示的集成效果。

## 子任务

1. 创建测试文件
2. 验证响应系统
3. 测试中断功能
4. 清理测试文件
"""
    
    with open(test_md, "w", encoding="utf-8") as f:
        f.write(test_content)
    
    print(f"创建测试文件: {test_md}")
    
    # 导入并测试收件箱
    try:
        from skills.task_inbox.inbox import TaskInbox
        
        inbox = TaskInbox(
            workspace=WORKSPACE,
            auto_execute=False,  # 只解析不执行，避免实际运行
            notify=False  # 不发送实际通知
        )
        
        print("\n手动投递测试文件...")
        record = await inbox.submit_file(test_md)
        
        print(f"\n任务记录:")
        print(f"  ID: {record.task_id}")
        print(f"  文件: {record.file_name}")
        print(f"  状态: {record.status}")
        print(f"  标题: {record.parsed_data.get('title', 'N/A')}")
        print(f"  子任务数: {len(record.parsed_data.get('subtasks', []))}")
        
        # 清理测试文件
        if test_md.exists():
            test_md.unlink()
            print(f"\n清理测试文件: {test_md}")
        
        return record.status == "parsed"
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("集成系统测试开始")
    print(f"工作目录: {WORKSPACE}")
    print(f"时间: 2026-03-06 23:55")
    print()
    
    results = []
    
    # 测试1: 响应系统
    print("🔧 测试1: 三层响应系统...")
    result1 = await test_responder_system()
    results.append(("三层响应系统", result1))
    
    # 测试2: 分阶段通知
    print("\n🔧 测试2: 分阶段通知系统...")
    result2 = await test_phased_notifier()
    results.append(("分阶段通知系统", result2))
    
    # 测试3: 收件箱集成
    print("\n🔧 测试3: 任务收件箱集成...")
    result3 = await test_inbox_integration()
    results.append(("任务收件箱集成", result3))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 所有集成测试通过！")
        print("\n现在Kylopro具备:")
        print("  1. 三层响应系统（情感回应/状态查询/真中断）")
        print("  2. 分阶段提示系统（5阶段+进度里程碑）")
        print("  3. 集成到任务收件箱（透明化执行过程）")
        print("  4. 保持实时响应（不'失联'）")
    else:
        print("⚠️  部分测试失败，需要进一步调试")
    
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)