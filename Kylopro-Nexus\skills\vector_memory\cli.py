#!/usr/bin/env python3
"""
向量记忆库命令行工具
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 添加技能目录到路径
skill_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(skill_dir))

from skills.vector_memory.memory import VectorMemory, create_vector_memory


async def cmd_init(args):
    """初始化向量记忆库"""
    print(f"初始化向量记忆库...")
    print(f"  数据库类型: {args.db}")
    print(f"  嵌入模型: {args.model}")
    print(f"  持久化路径: {args.path}")
    
    memory = VectorMemory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
        debug=args.debug,
    )
    
    success = await memory.initialize()
    
    if success:
        print("✅ 向量记忆库初始化成功!")
        
        # 显示统计信息
        stats = await memory.get_stats()
        print("\n初始统计:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        await memory.close()
        return 0
    else:
        print("❌ 向量记忆库初始化失败!")
        return 1


async def cmd_store(args):
    """存储记忆"""
    print(f"存储记忆...")
    
    memory = await create_vector_memory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
    )
    
    memory_id = await memory.store(
        content=args.content,
        key=args.key,
        metadata=json.loads(args.metadata) if args.metadata else {},
        importance=args.importance,
    )
    
    print(f"✅ 记忆存储成功!")
    print(f"  记忆ID: {memory_id}")
    print(f"  内容: {args.content[:50]}...")
    
    await memory.close()
    return 0


async def cmd_search(args):
    """搜索记忆"""
    print(f"搜索记忆: '{args.query}'")
    
    memory = await create_vector_memory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
    )
    
    results = await memory.search(
        query=args.query,
        limit=args.limit,
        min_score=args.min_score,
    )
    
    print(f"\n找到 {len(results)} 条相关记忆:")
    
    for i, result in enumerate(results):
        memory = result.memory
        print(f"\n{i+1}. [相关性: {result.relevance:.3f}, 相似度: {result.score:.3f}]")
        print(f"   ID: {memory.id}")
        print(f"   内容: {memory.content[:100]}...")
        print(f"   重要性: {memory.importance:.2f}")
        print(f"   元数据: {json.dumps(memory.metadata, ensure_ascii=False)[:100]}...")
    
    await memory.close()
    return 0


async def cmd_get(args):
    """获取特定记忆"""
    print(f"获取记忆: {args.id}")
    
    memory = await create_vector_memory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
    )
    
    memory_record = await memory.get(args.id)
    
    if memory_record:
        print(f"✅ 找到记忆:")
        print(f"  ID: {memory_record.id}")
        print(f"  内容: {memory_record.content}")
        print(f"  重要性: {memory_record.importance:.2f}")
        print(f"  访问次数: {memory_record.access_count}")
        print(f"  创建时间: {memory_record.created_at}")
        print(f"  最后访问: {memory_record.last_accessed}")
        print(f"  元数据: {json.dumps(memory_record.metadata, ensure_ascii=False, indent=2)}")
    else:
        print(f"❌ 未找到记忆: {args.id}")
    
    await memory.close()
    return 0


async def cmd_delete(args):
    """删除记忆"""
    print(f"删除记忆: {args.id}")
    
    memory = await create_vector_memory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
    )
    
    success = await memory.delete(args.id)
    
    if success:
        print(f"✅ 记忆删除成功: {args.id}")
    else:
        print(f"❌ 记忆删除失败: {args.id}")
    
    await memory.close()
    return 0


async def cmd_stats(args):
    """获取统计信息"""
    print("获取向量记忆库统计信息...")
    
    memory = await create_vector_memory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
    )
    
    stats = await memory.get_stats()
    
    print("\n📊 向量记忆库统计:")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")
    
    await memory.close()
    return 0


async def cmd_export(args):
    """导出记忆"""
    print(f"导出记忆到: {args.file}")
    
    memory = await create_vector_memory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
    )
    
    success = await memory.export_memories(args.file)
    
    if success:
        print(f"✅ 记忆导出成功!")
    else:
        print(f"❌ 记忆导出失败!")
    
    await memory.close()
    return 0


async def cmd_import(args):
    """导入记忆"""
    print(f"从文件导入记忆: {args.file}")
    
    memory = await create_vector_memory(
        db_type=args.db,
        embedding_model=args.model,
        persist_path=args.path,
    )
    
    success = await memory.import_memories(args.file)
    
    if success:
        print(f"✅ 记忆导入成功!")
    else:
        print(f"❌ 记忆导入失败!")
    
    await memory.close()
    return 0


async def cmd_test(args):
    """运行测试"""
    print("运行向量记忆库测试...")
    
    from skills.vector_memory.memory import test_vector_memory
    
    try:
        await test_vector_memory()
        print("✅ 测试通过!")
        return 0
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="向量记忆库命令行工具")
    parser.add_argument("--db", default="memory", help="数据库类型 (chromadb, faiss, memory)")
    parser.add_argument("--model", default="test", help="嵌入模型类型 (local, ollama, test)")
    parser.add_argument("--path", default="./data/memory", help="持久化路径")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # init 命令
    init_parser = subparsers.add_parser("init", help="初始化向量记忆库")
    init_parser.set_defaults(func=cmd_init)
    
    # store 命令
    store_parser = subparsers.add_parser("store", help="存储记忆")
    store_parser.add_argument("--content", required=True, help="记忆内容")
    store_parser.add_argument("--key", help="记忆键（可选）")
    store_parser.add_argument("--metadata", help="元数据 JSON 字符串")
    store_parser.add_argument("--importance", type=float, default=0.5, help="重要性分数 0-1")
    store_parser.set_defaults(func=cmd_store)
    
    # search 命令
    search_parser = subparsers.add_parser("search", help="搜索记忆")
    search_parser.add_argument("--query", required=True, help="搜索查询")
    search_parser.add_argument("--limit", type=int, default=5, help="返回结果数量")
    search_parser.add_argument("--min-score", type=float, default=0.3, help="最小相似度分数")
    search_parser.set_defaults(func=cmd_search)
    
    # get 命令
    get_parser = subparsers.add_parser("get", help="获取特定记忆")
    get_parser.add_argument("--id", required=True, help="记忆ID")
    get_parser.set_defaults(func=cmd_get)
    
    # delete 命令
    delete_parser = subparsers.add_parser("delete", help="删除记忆")
    delete_parser.add_argument("--id", required=True, help="记忆ID")
    delete_parser.set_defaults(func=cmd_delete)
    
    # stats 命令
    stats_parser = subparsers.add_parser("stats", help="获取统计信息")
    stats_parser.set_defaults(func=cmd_stats)
    
    # export 命令
    export_parser = subparsers.add_parser("export", help="导出记忆")
    export_parser.add_argument("--file", required=True, help="导出文件路径")
    export_parser.set_defaults(func=cmd_export)
    
    # import 命令
    import_parser = subparsers.add_parser("import", help="导入记忆")
    import_parser.add_argument("--file", required=True, help="导入文件路径")
    import_parser.set_defaults(func=cmd_import)
    
    # test 命令
    test_parser = subparsers.add_parser("test", help="运行测试")
    test_parser.set_defaults(func=cmd_test)
    
    # 解析参数
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # 运行命令
    try:
        return asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print("\n操作被用户中断")
        return 130
    except Exception as e:
        print(f"错误: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())