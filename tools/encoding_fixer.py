#!/usr/bin/env python3
"""
编码修复工具 - 自动处理Windows编码问题
"""

import sys
import os
import locale
import subprocess

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

def run_safe_command(cmd, cwd=None, timeout=30):
    """安全的命令执行"""
    encoding = get_system_encoding()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding=encoding,
            errors='replace',
            timeout=timeout,
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

def fix_file_encoding(filepath):
    """修复文件编码"""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    except Exception as e:
        return False

if __name__ == "__main__":
    safe_print("编码修复工具测试")
    safe_print("中文测试：你好，世界！")
    
    result = run_safe_command("python --version")
    safe_print(f"Python版本: {result.stdout}")
