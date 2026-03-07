#!/usr/bin/env python3
"""
简单测试IDE桥接器
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_simple():
    """简单测试文件读写"""
    try:
        print("1. 测试IDE桥接器...")
        from skills.ide_bridge.bridge import IDEBridge
        
        bridge = IDEBridge(".")
        
        print("2. 获取文件树...")
        tree = bridge.get_file_tree()
        print(f"文件树预览:\n{tree[:500]}...")
        
        print("3. 创建测试文件...")
        test_content = '''#!/usr/bin/env python3
"""
测试Antigravity连接
"""

import subprocess
import sys

def test_antigravity():
    """测试Antigravity命令行调用"""
    try:
        # Antigravity路径
        antigravity_path = r"C:\\Users\\qianchen\\AppData\\Local\\Programs\\Antigravity\\bin\\antigravity.exe"
        
        # 测试版本
        result = subprocess.run([antigravity_path, "--version"], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Antigravity版本: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Antigravity调用失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        return False

if __name__ == "__main__":
    test_antigravity()'''
        
        bridge.write_file("test_antigravity_simple.py", test_content)
        print("✅ 测试文件创建成功")
        
        print("4. 读取测试文件...")
        content = bridge.read_file("test_antigravity_simple.py")
        print(f"读取内容预览:\n{content[:200]}...")
        
        print("✅ IDE桥接器测试完成！")
        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_simple()