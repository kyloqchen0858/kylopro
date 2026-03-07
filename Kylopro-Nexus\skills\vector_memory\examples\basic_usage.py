#!/usr/bin/env python3
"""
向量记忆库基本使用示例
"""

import asyncio
import sys
from pathlib import Path

# 添加技能目录到路径
skill_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(skill_dir))

from skills.vector_memory.memory import VectorMemory


async def main():
    """主函数"""
    print("向量记忆库基本使用示例")
    print("="*60)
    
    # 1. 初始化记忆库（使用内存存储和测试嵌入模型）
    print("\n1. 初始化向量记忆库...")
    memory = VectorMemory(
        db_type="memory",  # 内存存储，用于测试
        embedding_model="test",  # 测试用随机向量
        debug=True,
    )
    
    await memory.initialize()
    print("✅ 记忆库初始化成功")
    
    # 2. 存储一些记忆
    print("\n2. 存储记忆...")
    
    memories = [
        {
            "content": "用户喜欢简洁的回答方式，讨厌冗长的解释",
            "metadata": {"category": "preference", "user": "qianchen"},
            "importance": 0.8,
        },
        {
            "content": "Kylopro项目目标是创建全能AI助手，能够自主学习和进化",
            "metadata": {"category": "project", "project": "Kylopro-Nexus"},
            "importance": 0.9,
        },
        {
            "content": "Trae是AI编程助手，支持MCP协议，可以协同开发",
            "metadata": {"category": "tool", "tool": "Trae"},
            "importance": 0.7,
        },
        {
            "content": "Antigravity是VS Code变体，有Pro账户，支持Claude Opus模型",
            "metadata": {"category": "tool", "tool": "Antigravity"},
            "importance": 0.8,
        },
        {
            "content": "用户通过Telegram远程连接，电脑在熄屏状态下工作",
            "metadata": {"category": "context", "connection": "telegram"},
            "importance": 0.6,
        },
    ]
    
    memory_ids = await memory.batch_store(memories)
    print(f"✅ 存储了 {len(memory_ids)} 条记忆")
    
    # 3. 搜索记忆
    print("\n3. 搜索记忆测试...")
    
    test_queries = [
        "简洁回答",
        "AI助手项目",
        "编程工具",
        "远程连接",
    ]
    
    for query in test_queries:
        print(f"\n搜索: '{query}'")
        results = await memory.search(query, limit=2)
        
        if results:
            for i, result in enumerate(results):
                print(f"  {i+1}. {result.memory.content[:60]}... (相关性: {result.relevance:.2f})")
        else:
            print("  未找到相关记忆")
    
    # 4. 获取上下文
    print("\n4. 获取上下文测试...")
    
    context_queries = [
        "用户偏好",
        "项目信息",
        "可用工具",
    ]
    
    for query in context_queries:
        print(f"\n查询: '{query}'")
        context = await memory.get_context(query, max_tokens=300)
        
        if context:
            print(f"  相关上下文 ({len(context)} 字符):")
            print(f"  {context[:150]}...")
        else:
            print("  无相关上下文")
    
    # 5. 获取和更新记忆
    print("\n5. 获取和更新记忆测试...")
    
    if memory_ids:
        # 获取第一条记忆
        memory_id = memory_ids[0]
        memory_record = await memory.get(memory_id)
        
        if memory_record:
            print(f"获取记忆: {memory_id}")
            print(f"  原始内容: {memory_record.content}")
            print(f"  重要性: {memory_record.importance:.2f}")
            
            # 更新记忆
            print("更新记忆...")
            success = await memory.update(
                memory_id=memory_id,
                content="用户非常喜欢简洁的回答方式，特别讨厌冗长的解释",
                importance=0.85,
            )
            
            if success:
                updated_record = await memory.get(memory_id)
                print(f"✅ 更新成功:")
                print(f"  新内容: {updated_record.content}")
                print(f"  新重要性: {updated_record.importance:.2f}")
    
    # 6. 统计信息
    print("\n6. 统计信息:")
    stats = await memory.get_stats()
    
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")
    
    # 7. 清理和关闭
    print("\n7. 清理测试...")
    
    if memory_ids:
        # 删除一条记忆
        memory_id_to_delete = memory_ids[-1]
        success = await memory.delete(memory_id_to_delete)
        
        if success:
            print(f"✅ 删除记忆: {memory_id_to_delete}")
            
            # 验证删除
            deleted_record = await memory.get(memory_id_to_delete)
            if deleted_record is None:
                print(f"✅ 验证: 记忆已成功删除")
            else:
                print(f"❌ 验证: 记忆仍然存在")
    
    # 8. 关闭记忆库
    print("\n8. 关闭记忆库...")
    await memory.close()
    print("✅ 记忆库已关闭")
    
    print("\n" + "="*60)
    print("示例完成!")
    print("\n现在你可以:")
    print("  1. 使用ChromaDB作为生产数据库")
    print("  2. 使用本地嵌入模型（如BGE-small-zh）")
    print("  3. 集成到Kylopro核心中")
    print("  4. 添加记忆自动清理和优化")


if __name__ == "__main__":
    asyncio.run(main())