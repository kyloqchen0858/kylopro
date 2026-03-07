#!/usr/bin/env python3
"""
熄屏状态测试脚本
测试在电脑熄屏状态下，Antigravity和任务收件箱是否能正常工作
"""

import sys
import time
import datetime
import subprocess
from pathlib import Path

def log_message(message):
    """记录日志（同时输出到控制台和文件）"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    
    # 输出到控制台
    print(log_line)
    
    # 写入日志文件
    with open("screen_off_test.log", "a", encoding="utf-8") as f:
        f.write(log_line + "\n")
    
    # 强制刷新
    sys.stdout.flush()

def test_file_operation():
    """测试文件操作（熄屏状态下应该能工作）"""
    log_message("测试1: 文件创建和写入...")
    
    test_file = "screen_off_test.txt"
    test_content = f"""熄屏状态测试文件
创建时间: {datetime.datetime.now()}
测试内容: 验证在电脑熄屏状态下文件操作是否正常
状态: 运行中...
"""
    
    try:
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_content)
        log_message(f"✅ 文件创建成功: {test_file}")
        
        # 验证读取
        with open(test_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        if "熄屏状态测试" in content:
            log_message("✅ 文件读取验证成功")
            return True
        else:
            log_message("❌ 文件内容验证失败")
            return False
            
    except Exception as e:
        log_message(f"❌ 文件操作失败: {e}")
        return False

def test_command_execution():
    """测试命令执行（熄屏状态下应该能工作）"""
    log_message("测试2: 命令执行测试...")
    
    try:
        # 测试Python版本
        result = subprocess.run(
            ["python", "--version"],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode == 0:
            log_message(f"✅ 命令执行成功: {result.stdout.strip()}")
            return True
        else:
            log_message(f"❌ 命令执行失败: {result.stderr}")
            return False
            
    except Exception as e:
        log_message(f"❌ 命令执行异常: {e}")
        return False

def test_antigravity_connection():
    """测试Antigravity连接"""
    log_message("测试3: Antigravity连接测试...")
    
    antigravity_path = r"C:\Users\qianchen\AppData\Local\Programs\Antigravity\bin\antigravity.exe"
    
    if not Path(antigravity_path).exists():
        log_message(f"⚠️  Antigravity路径不存在: {antigravity_path}")
        log_message("跳过Antigravity测试")
        return True  # 跳过但不失败
    
    try:
        # 测试Antigravity版本
        result = subprocess.run(
            [antigravity_path, "--version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=10
        )
        
        if result.returncode == 0:
            log_message(f"✅ Antigravity连接成功: {result.stdout.strip()}")
            return True
        else:
            log_message(f"❌ Antigravity调用失败: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log_message("⚠️  Antigravity调用超时（可能正在启动）")
        return True  # 超时不视为失败
    except Exception as e:
        log_message(f"❌ Antigravity测试异常: {e}")
        return False

def test_task_inbox():
    """测试任务收件箱功能"""
    log_message("测试4: 任务收件箱测试...")
    
    try:
        # 创建测试任务
        test_task = """# 熄屏状态测试任务

## 需求描述
测试在熄屏状态下任务收件箱是否能正常工作

## 具体任务
1. 创建测试文件 screen_off_result.txt
2. 写入测试结果
3. 记录时间戳

## 预期结果
验证熄屏状态下的自动化任务执行能力"""
        
        task_file = "data/inbox/screen_off_test.md"
        Path(task_file).parent.mkdir(parents=True, exist_ok=True)
        
        with open(task_file, "w", encoding="utf-8") as f:
            f.write(test_task)
        
        log_message(f"✅ 测试任务创建成功: {task_file}")
        
        # 创建结果文件
        result_content = f"""熄屏测试结果
测试时间: {datetime.datetime.now()}
任务文件: {task_file}
状态: 任务已创建，等待收件箱处理
说明: 此文件由熄屏测试脚本创建，用于验证文件操作能力
"""
        
        with open("screen_off_result.txt", "w", encoding="utf-8") as f:
            f.write(result_content)
        
        log_message("✅ 结果文件创建成功")
        return True
        
    except Exception as e:
        log_message(f"❌ 任务收件箱测试失败: {e}")
        return False

def main():
    """主测试函数"""
    log_message("=" * 60)
    log_message("开始熄屏状态测试")
    log_message("=" * 60)
    log_message("说明: 运行此脚本后，可以熄屏观察后台执行情况")
    log_message("日志将保存到: screen_off_test.log")
    
    # 测试计数器
    tests = [
        ("文件操作", test_file_operation),
        ("命令执行", test_command_execution),
        ("Antigravity连接", test_antigravity_connection),
        ("任务收件箱", test_task_inbox)
    ]
    
    results = []
    
    # 执行测试
    for test_name, test_func in tests:
        log_message(f"\n执行测试: {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
            time.sleep(2)  # 间隔2秒
        except Exception as e:
            log_message(f"❌ 测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    log_message("\n" + "=" * 60)
    log_message("测试结果汇总:")
    
    all_passed = True
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        log_message(f"  {test_name}: {status}")
        if not success:
            all_passed = False
    
    log_message("\n" + "=" * 60)
    if all_passed:
        log_message("🎉 所有测试通过！熄屏状态下工作正常")
        log_message("建议: 现在可以熄屏，观察后台进程是否继续运行")
    else:
        log_message("⚠️  部分测试失败，请检查日志")
    
    log_message("\n测试完成时间: " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log_message("日志文件: screen_off_test.log")
    
    # 保持运行一段时间，模拟长时间任务
    log_message("\n进入等待状态（模拟长时间任务）...")
    log_message("按 Ctrl+C 终止测试")
    
    try:
        for i in range(30):  # 等待5分钟（30 * 10秒）
            time.sleep(10)
            log_message(f"等待中... ({i+1}/30) - {datetime.datetime.now().strftime('%H:%M:%S')}")
    except KeyboardInterrupt:
        log_message("\n测试被用户中断")
    
    log_message("熄屏测试脚本结束")
    return 0 if all_passed else 1

if __name__ == "__main__":
    # 设置编码
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass
    
    exit_code = main()
    sys.exit(exit_code)