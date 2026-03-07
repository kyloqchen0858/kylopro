#!/usr/bin/env python3
"""
快速测试 Kylopro 核心功能
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

async def quick_test():
    """快速测试核心功能"""
    try:
        print("1. 测试双核路由 Provider...")
        from core.provider import KyloproProvider
        provider = KyloproProvider()
        
        print("2. 测试连通性...")
        result = await provider.test_connection()
        print(f"连通性测试结果: {result}")
        
        print("3. 测试简单对话...")
        messages = [{"role": "user", "content": "你好，简单介绍一下你自己"}]
        response = await provider.chat(messages, task_type="auto")
        print(f"Kylopro回复: {response.get('content', '')[:100]}...")
        
        print("✅ 核心功能测试通过！")
        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(quick_test())