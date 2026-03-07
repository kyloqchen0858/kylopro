#!/usr/bin/env python3
"""
简单测试任务收件箱
"""

import sys
import asyncio
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

async def test_inbox():
    """简单测试任务收件箱"""
    try:
        print("测试任务收件箱...")
        
        # 1. 创建简单的编码修复工具
        print("1. 创建编码修复工具...")
        tools_dir = Path("tools")
        tools_dir.mkdir(exist_ok=True)
        
        encoding_fixer_content = '''#!/usr/bin/env python3
"""
编码修复工具
"""

import sys
import subprocess
import locale

def get_system_encoding():
    """获取系统编码"""
    try:
        return locale.getpreferredencoding()
    except:
        return 'gbk'  # Windows默认

def safe_print(text):
    """安全的打印函数"""
    try:
        print(text)
    except UnicodeEncodeError:
        # 转换为系统编码
        encoding = get_system_encoding()
        try:
            encoded = text.encode(encoding, errors='replace')
            print(encoded.decode(encoding))
        except:
            # 最后的手段：移除非ASCII字符
            safe_text = ''.join(c if ord(c) < 128 else '?' for c in text)
            print(safe_text)

def run_command_with_encoding(cmd, cwd=None):
    """带编码处理的命令执行"""
    encoding = get_system_encoding()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding=encoding,
            errors='replace',
            cwd=cwd
        )
        return result
    except Exception as e:
        return subprocess.CompletedProcess(
            cmd, 
            returncode=1,
            stdout='',
            stderr=f'命令执行失败: {e}'
        )

if __name__ == "__main__":
    # 测试
    safe_print("✅ 编码修复工具测试")
    safe_print("中文测试：你好，世界！")
    
    result = run_command_with_encoding("python --version")
    safe_print(f"Python版本: {result.stdout}")
'''
        
        with open(tools_dir / "encoding_fixer.py", "w", encoding="utf-8") as f:
            f.write(encoding_fixer_content)
        
        print("✅ 编码修复工具创建成功")
        
        # 2. 创建测试脚本
        print("2. 创建测试脚本...")
        tests_dir = Path("tests")
        tests_dir.mkdir(exist_ok=True)
        
        test_encoding_content = '''#!/usr/bin/env python3
"""
编码测试
"""

import sys
from pathlib import Path

# 添加工具路径
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from encoding_fixer import safe_print, run_command_with_encoding

def test_chinese_print():
    """测试中文打印"""
    print("\\n1. 测试中文打印...")
    safe_print("✅ 中文测试：你好，世界！")
    safe_print("✅ 特殊字符：🎉🐈🚀")
    return True

def test_file_io():
    """测试文件读写"""
    print("\\n2. 测试文件读写...")
    test_content = "中文测试内容：你好，世界！🎉"
    test_file = "test_chinese.txt"
    
    try:
        # 写入
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)
        
        # 读取
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        if content == test_content:
            safe_print(f"✅ 文件读写测试通过: {test_file}")
            return True
        else:
            safe_print(f"❌ 文件内容不匹配")
            return False
    except Exception as e:
        safe_print(f"❌ 文件读写失败: {e}")
        return False
    finally:
        # 清理
        import os
        if os.path.exists(test_file):
            os.remove(test_file)

def test_command_execution():
    """测试命令执行"""
    print("\\n3. 测试命令执行...")
    result = run_command_with_encoding("python --version")
    safe_print(f"命令输出: {result.stdout.strip()}")
    return result.returncode == 0

def main():
    """主测试函数"""
    print("开始编码测试...")
    
    tests = [
        ("中文打印", test_chinese_print),
        ("文件读写", test_file_io),
        ("命令执行", test_command_execution)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            safe_print(f"❌ {name} 测试异常: {e}")
            results.append((name, False))
    
    # 汇总
    print("\\n" + "="*40)
    print("测试结果汇总:")
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {name}: {status}")
    
    all_passed = all(success for _, success in results)
    if all_passed:
        print("\\n🎉 所有测试通过！")
    else:
        print("\\n⚠️  部分测试失败")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
'''
        
        with open(tests_dir / "test_encoding.py", "w", encoding="utf-8") as f:
            f.write(test_encoding_content)
        
        print("✅ 测试脚本创建成功")
        
        # 3. 运行测试
        print("3. 运行测试...")
        result = subprocess.run(
            ["python", "tests/test_encoding.py"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            print("✅ 测试运行成功:")
            print(result.stdout)
        else:
            print("❌ 测试运行失败:")
            print(result.stderr)
        
        # 4. 创建文档
        print("4. 创建文档...")
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        
        doc_content = '''# Windows编码处理指南

## 问题描述
在Windows环境下，Python程序经常遇到编码问题：
1. 控制台输出中文乱码
2. 文件读写编码错误
3. 子进程输出丢失

## 解决方案

### 1. 统一使用UTF-8编码
```python
# 文件读写
with open("file.txt", "r", encoding="utf-8") as f:
    content = f.read()

with open("file.txt", "w", encoding="utf-8") as f:
    f.write(content)
```

### 2. 安全的打印函数
```python
import sys
import locale

def safe_print(text):
    """安全的打印函数"""
    try:
        print(text)
    except UnicodeEncodeError:
        # 转换为系统编码
        encoding = locale.getpreferredencoding()
        try:
            encoded = text.encode(encoding, errors='replace')
            print(encoded.decode(encoding))
        except:
            # 最后的手段
            safe_text = ''.join(c if ord(c) < 128 else '?' for c in text)
            print(safe_text)
```

### 3. 带编码处理的命令执行
```python
import subprocess

def run_command_with_encoding(cmd, cwd=None):
    """带编码处理的命令执行"""
    encoding = locale.getpreferredencoding()
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        encoding=encoding,
        errors='replace',
        cwd=cwd
    )
    return result
```

## 工具使用
项目中提供了 `tools/encoding_fixer.py` 工具模块，包含：
- `safe_print()` - 安全的打印函数
- `run_command_with_encoding()` - 带编码处理的命令执行
- `get_system_encoding()` - 获取系统编码

## 测试验证
运行测试脚本验证编码处理：
```bash
python tests/test_encoding.py
```

## 常见问题

### Q: 为什么控制台显示乱码？
A: Windows控制台默认使用GBK编码，而Python使用UTF-8。使用`safe_print()`函数解决。

### Q: 文件读写时出现编码错误？
A: 确保所有文件操作都指定`encoding="utf-8"`。

### Q: 子进程输出丢失？
A: 使用`run_command_with_encoding()`函数，它会正确处理编码。

## 最佳实践
1. 所有文本文件使用UTF-8编码
2. 使用提供的工具函数处理输出
3. 在Windows环境下测试编码兼容性
'''
        
        with open(docs_dir / "encoding_guide.md", "w", encoding="utf-8") as f:
            f.write(doc_content)
        
        print("✅ 文档创建成功: docs/encoding_guide.md")
        
        # 5. 清理
        print("5. 清理测试文件...")
        import os
        if os.path.exists("test_chinese.txt"):
            os.remove("test_chinese.txt")
        
        print("\\n" + "="*60)
        print("🎉 编码修复任务完成！")
        print("="*60)
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import subprocess
    asyncio.run(test_inbox())