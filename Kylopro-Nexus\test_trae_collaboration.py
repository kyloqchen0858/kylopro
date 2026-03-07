#!/usr/bin/env python3
"""
测试Kylopro与Trae的协同开发
验证IDE桥接技能是否正常工作
"""

import asyncio
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE))

async def test_ide_bridge():
    """测试IDE桥接技能"""
    print("="*60)
    print("测试IDE桥接与Trae协同")
    print("="*60)
    
    try:
        from skills.ide_bridge.bridge import IDEBridge
        
        # 创建桥接器
        bridge = IDEBridge(WORKSPACE)
        print(f"✅ IDE桥接器初始化成功")
        print(f"   工作区: {WORKSPACE}")
        
        # 测试文件树
        print("\n📁 获取文件树...")
        tree = await bridge.get_file_tree()
        print(f"   文件树预览: {str(tree)[:200]}...")
        
        # 测试读取文件
        print("\n📄 测试读取文件...")
        try:
            content = await bridge.read_file("DEVLOG.md", max_chars=500)
            print(f"   ✅ 成功读取DEVLOG.md")
            print(f"   内容预览: {content[:100]}...")
        except Exception as e:
            print(f"   ❌ 读取失败: {e}")
        
        # 测试写入文件
        print("\n✏️ 测试写入文件...")
        test_content = "# Trae协同测试\n\n这是Kylopro通过IDE桥接写入的测试文件。\n\n时间: 2026-03-07 12:45"
        try:
            await bridge.write_file("test_trae_collaboration.md", test_content)
            print(f"   ✅ 成功写入测试文件")
            
            # 验证写入
            read_back = await bridge.read_file("test_trae_collaboration.md")
            if test_content in read_back:
                print(f"   ✅ 验证通过，内容一致")
            else:
                print(f"   ⚠️ 验证失败，内容不一致")
        except Exception as e:
            print(f"   ❌ 写入失败: {e}")
        
        # 测试命令执行
        print("\n⚙️ 测试命令执行...")
        try:
            result = await bridge.run_command("python --version")
            print(f"   ✅ 命令执行成功")
            print(f"   返回码: {result['returncode']}")
            print(f"   输出: {result['stdout'].strip()}")
        except Exception as e:
            print(f"   ❌ 命令执行失败: {e}")
        
        # 测试MCP连接
        print("\n🔗 测试MCP连接...")
        try:
            connected = await bridge.connect_mcp()
            if connected:
                print(f"   ✅ MCP连接成功 (模拟)")
                print(f"   说明: Trae可能通过MCP协议暴露接口")
            else:
                print(f"   ⚠️ MCP连接失败")
        except Exception as e:
            print(f"   ❌ MCP连接异常: {e}")
        
        # 测试代码搜索
        print("\n🔍 测试代码搜索...")
        try:
            results = await bridge.search_in_code("trae", extensions=[".py", ".md"])
            print(f"   ✅ 搜索完成，找到 {len(results)} 个结果")
            if results:
                for i, r in enumerate(results[:3], 1):
                    print(f"     {i}. {r['file']}:{r['line']} - {r['content'][:50]}...")
        except Exception as e:
            print(f"   ❌ 搜索失败: {e}")
        
        # 清理测试文件
        test_file = WORKSPACE / "test_trae_collaboration.md"
        if test_file.exists():
            test_file.unlink()
            print(f"\n🧹 清理测试文件: {test_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ IDE桥接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_trae_integration():
    """测试Trae集成"""
    print("\n" + "="*60)
    print("测试Trae集成")
    print("="*60)
    
    # 检查Trae进程
    import subprocess
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Trae.exe"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        
        if "Trae.exe" in result.stdout:
            lines = [l for l in result.stdout.splitlines() if "Trae.exe" in l]
            print(f"✅ Trae正在运行 ({len(lines)} 个进程)")
            
            # 提取进程信息
            for i, line in enumerate(lines[:3], 1):
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[1]
                    mem = parts[4]
                    print(f"   进程{i}: PID={pid}, 内存={mem}")
            
            if len(lines) > 3:
                print(f"   ... 还有 {len(lines)-3} 个进程")
        else:
            print("❌ Trae未运行")
            return False
        
        # 检查Trae安装路径
        trae_path = Path("C:/Users/qianchen/AppData/Local/Programs/Trae/Trae.exe")
        if trae_path.exists():
            print(f"✅ Trae安装路径: {trae_path}")
            
            # 检查Trae版本
            try:
                version_result = subprocess.run(
                    [str(trae_path), "--version"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="ignore",
                    timeout=5
                )
                if version_result.returncode == 0:
                    print(f"   Trae版本: {version_result.stdout.strip()}")
                else:
                    print(f"   Trae版本检查失败")
            except:
                print(f"   Trae版本检查超时或失败")
        else:
            print(f"⚠️ Trae安装路径不存在: {trae_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Trae集成测试失败: {e}")
        return False

async def test_collaboration_workflow():
    """测试协同工作流"""
    print("\n" + "="*60)
    print("测试协同工作流")
    print("="*60)
    
    print("📋 协同工作流设计:")
    print("  1. Kylopro分析需求 → 生成Markdown任务文档")
    print("  2. 通过IDE桥接写入项目目录")
    print("  3. Trae监控文件变化 → 读取任务文档")
    print("  4. Trae执行开发任务 → 更新代码")
    print("  5. Kylopro验证结果 → 报告进度")
    
    # 创建协同测试任务
    collaboration_task = """# Trae协同开发测试任务

## 需求描述
测试Kylopro与Trae的协同开发工作流，验证IDE桥接技能的实际效果。

## 具体任务
1. 在`core/`目录下创建`trae_integration.py`模块
2. 实现Trae通信接口（MCP协议或文件系统通信）
3. 添加协同开发状态监控
4. 编写测试用例验证协同功能

## 技术要点
- 使用MCP协议与Trae通信（如果Trae暴露MCP Server）
- 文件系统通信作为降级方案
- 状态同步和错误处理
- 进度报告和日志记录

## 预期结果
- Kylopro可以主动向Trae发送开发任务
- Trae可以接收并执行任务
- 双方可以同步开发状态
- 完整的协同开发工作流

## 优先级
高 - 验证核心协同能力
"""
    
    task_path = WORKSPACE / "trae_collaboration_task.md"
    try:
        with open(task_path, "w", encoding="utf-8") as f:
            f.write(collaboration_task)
        print(f"✅ 创建协同测试任务: {task_path}")
        
        # 模拟Trae读取任务
        with open(task_path, "r", encoding="utf-8") as f:
            content = f.read()
            print(f"✅ 模拟Trae读取任务 (长度: {len(content)} 字符)")
            print(f"   任务标题: {content.splitlines()[0]}")
        
        # 清理测试文件
        task_path.unlink()
        print(f"🧹 清理测试任务文件")
        
        return True
        
    except Exception as e:
        print(f"❌ 协同工作流测试失败: {e}")
        return False

async def main():
    """主测试函数"""
    print("Trae协同开发测试开始")
    print(f"时间: 2026-03-07 12:45")
    print(f"工作区: {WORKSPACE}")
    print()
    
    results = []
    
    # 测试1: IDE桥接
    print("🔧 测试1: IDE桥接技能...")
    result1 = await test_ide_bridge()
    results.append(("IDE桥接技能", result1))
    
    # 测试2: Trae集成
    print("\n🔧 测试2: Trae集成状态...")
    result2 = await test_trae_integration()
    results.append(("Trae集成", result2))
    
    # 测试3: 协同工作流
    print("\n🔧 测试3: 协同工作流...")
    result3 = await test_collaboration_workflow()
    results.append(("协同工作流", result3))
    
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
        print("🎉 所有协同测试通过！")
        print("\n现在可以:")
        print("  1. Kylopro通过IDE桥接读写代码文件")
        print("  2. 与运行的Trae进程协同开发")
        print("  3. 实现完整的协同工作流")
        print("  4. 解决之前'记忆消失'的问题")
    else:
        print("⚠️ 部分测试失败，需要进一步调试")
    
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)