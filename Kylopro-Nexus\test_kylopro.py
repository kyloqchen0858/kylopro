#!/usr/bin/env python3
"""
Kylopro 快速测试脚本
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

async def test_provider():
    """测试双核路由 Provider"""
    try:
        from core.provider import KyloproProvider
        
        print("测试 Kylopro 双核路由 Provider...")
        provider = KyloproProvider()
        
        # 测试连通性
        print("测试连通性...")
        result = await provider.test_connection()
        print(result)
        
        # 测试简单对话
        print("\n测试简单对话...")
        messages = [{"role": "user", "content": "你好，我是人类，请简单介绍一下你自己"}]
        response = await provider.chat(messages, task_type="auto")
        print("Kylopro:", response.get("content", "")[:200])
        
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_task_inbox():
    """测试任务收件箱"""
    try:
        from skills.task_inbox.inbox import TaskInbox
        
        print("\n测试任务收件箱...")
        inbox = TaskInbox(workspace=Path(__file__).parent)
        
        # 创建测试需求文档
        test_md = Path(__file__).parent / "data" / "inbox" / "test_hello.md"
        test_md.parent.mkdir(parents=True, exist_ok=True)
        test_md.write_text("""# 测试任务

## 需求描述
创建一个简单的 hello.py 文件，打印 "Hello from Kylopro!"

## 任务清单
1. 创建 hello.py 文件
2. 写入打印语句
3. 运行测试
""", encoding="utf-8")
        
        print(f"📄 创建测试需求文档: {test_md}")
        print("📤 投递任务...")
        
        # 投递任务
        record = await inbox.submit_file(str(test_md))
        print(f"✅ 任务状态: {record.status}")
        
        if record.result:
            for r in record.result.get("results", []):
                icon = "✅" if r["status"] == "success" else "❌"
                print(f"  {icon} #{r['id']} {r['action']}: {r['output'][:80]}")
        
        return True
    except Exception as e:
        print(f"❌ 任务收件箱测试失败: {e}")
        return False

async def main():
    print("Kylopro 启动测试")
    print("=" * 50)
    
    # 测试 Provider
    if not await test_provider():
        print("\n⚠️  Provider 测试失败，但继续测试其他组件...")
    
    # 测试任务收件箱
    if not await test_task_inbox():
        print("\n⚠️  任务收件箱测试失败")
    
    print("\n" + "=" * 50)
    print("🎉 Kylopro 测试完成！")
    print("\n📋 下一步:")
    print("1. 运行完整引擎: python -m core.engine")
    print("2. 启动任务收件箱: python skills/task_inbox/inbox.py")
    print("3. 投递需求文档到 data/inbox/ 目录")

if __name__ == "__main__":
    asyncio.run(main())