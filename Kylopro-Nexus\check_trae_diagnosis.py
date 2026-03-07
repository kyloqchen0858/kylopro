#!/usr/bin/env python3
"""
检查Trae的诊断结果并模拟鼠标操作
"""

import asyncio
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent
sys.path.insert(0, str(WORKSPACE))

async def check_trae_diagnosis():
    """检查Trae的诊断结果"""
    print("="*60)
    print("检查Trae的诊断结果")
    print("="*60)
    
    try:
        # 导入Vision RPA技能
        from skills.vision_rpa.vision import VisionRPA
        
        # 创建RPA实例
        rpa = VisionRPA()
        print("✅ Vision RPA技能加载成功")
        
        # 1. 查找Trae窗口
        print("\n🔍 查找Trae窗口...")
        
        # 先截图整个屏幕
        screenshot_path = WORKSPACE / "trae_screenshot.png"
        await rpa.screenshot(str(screenshot_path))
        print(f"   ✅ 截图保存到: {screenshot_path}")
        
        # 2. 尝试OCR识别Trae界面
        print("\n🔤 OCR识别Trae界面文字...")
        try:
            # 假设Trae在屏幕左上角区域
            ocr_text = await rpa.screenshot_ocr(region=(0, 0, 1200, 800))
            print(f"   ✅ OCR识别完成")
            
            # 分析OCR结果
            lines = ocr_text.split('\n')
            print(f"   识别到 {len(lines)} 行文字")
            
            # 查找诊断相关关键词
            keywords = ["诊断", "diagnos", "检查", "report", "分析", "问题", "error", "warning"]
            found_lines = []
            
            for line in lines:
                if any(keyword.lower() in line.lower() for keyword in keywords):
                    found_lines.append(line.strip())
            
            if found_lines:
                print(f"\n📋 发现诊断相关内容:")
                for i, line in enumerate(found_lines[:10], 1):
                    print(f"   {i}. {line}")
            else:
                print(f"   ⚠️ 未找到明显的诊断内容")
                
            # 保存OCR结果
            ocr_path = WORKSPACE / "trae_ocr_result.txt"
            with open(ocr_path, "w", encoding="utf-8") as f:
                f.write(ocr_text)
            print(f"   📄 OCR结果保存到: {ocr_path}")
            
        except Exception as e:
            print(f"   ❌ OCR识别失败: {e}")
        
        # 3. 模拟鼠标操作
        print("\n🖱️ 模拟鼠标操作...")
        
        # 获取屏幕尺寸
        screen_width, screen_height = rpa.get_screen_size()
        print(f"   屏幕尺寸: {screen_width}x{screen_height}")
        
        # 模拟鼠标移动到Trae可能的位置（假设在左上角）
        trae_x, trae_y = 100, 100
        print(f"   移动鼠标到 ({trae_x}, {trae_y})...")
        rpa.move_to(trae_x, trae_y)
        
        # 模拟鼠标滚动（向下滚动）
        print("   模拟鼠标滚动（向下）...")
        rpa.scroll(-500)  # 负值向下滚动
        
        # 等待一下
        await asyncio.sleep(1)
        
        # 再次截图滚动后的内容
        scrolled_screenshot = WORKSPACE / "trae_scrolled.png"
        await rpa.screenshot(str(scrolled_screenshot))
        print(f"   ✅ 滚动后截图: {scrolled_screenshot}")
        
        # 4. 检查Trae进程信息
        print("\n📊 检查Trae进程信息...")
        import psutil
        
        trae_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'create_time']):
            try:
                if proc.info['name'] and 'trae' in proc.info['name'].lower():
                    trae_processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if trae_processes:
            print(f"   ✅ 找到 {len(trae_processes)} 个Trae进程")
            for proc in trae_processes[:3]:
                mem_mb = proc['memory_info'].rss / 1024 / 1024
                print(f"     PID: {proc['pid']}, 内存: {mem_mb:.1f} MB")
        else:
            print("   ❌ 未找到Trae进程")
        
        # 5. 检查Trae日志文件
        print("\n📝 检查Trae日志文件...")
        trae_log_paths = [
            Path("C:/Users/qianchen/AppData/Local/Trae/logs"),
            Path("C:/Users/qianchen/AppData/Roaming/Trae/logs"),
            Path("C:/Users/qianchen/.trae/logs"),
        ]
        
        found_logs = []
        for log_path in trae_log_paths:
            if log_path.exists():
                print(f"   ✅ 找到日志目录: {log_path}")
                try:
                    log_files = list(log_path.glob("*.log"))
                    for log_file in log_files[:3]:
                        found_logs.append(log_file)
                        print(f"     - {log_file.name}")
                except:
                    pass
        
        if found_logs:
            # 读取最新的日志文件
            latest_log = max(found_logs, key=lambda p: p.stat().st_mtime)
            print(f"\n📖 读取最新日志: {latest_log}")
            try:
                with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-20:]  # 最后20行
                    print(f"   最后{len(lines)}行日志:")
                    for line in lines:
                        if any(keyword in line.lower() for keyword in ["error", "warn", "diagnos", "check"]):
                            print(f"     ⚠️ {line.strip()}")
            except Exception as e:
                print(f"   读取日志失败: {e}")
        
        # 6. 生成诊断报告
        print("\n" + "="*60)
        print("Trae诊断检查完成")
        print("="*60)
        
        report = f"""# Trae诊断检查报告

## 检查时间
{asyncio.get_event_loop().time()}

## 检查结果
1. **屏幕截图**: 已保存 ({screenshot_path.name}, {scrolled_screenshot.name})
2. **OCR识别**: 完成 ({len(lines) if 'lines' in locals() else 0} 行文字)
3. **鼠标操作**: 模拟滚动完成
4. **进程状态**: {len(trae_processes)} 个Trae进程运行中
5. **日志文件**: {len(found_logs)} 个日志文件找到

## 发现的问题
{chr(10).join(f"- {line}" for line in found_lines[:5]) if found_lines else "- 未发现明显问题"}

## 建议操作
1. 手动查看Trae界面中的诊断结果
2. 检查Trae是否连接到正确的项目
3. 验证MCP协议是否正常工作
4. 确认Kylopro与Trae的协同配置

## 下一步
- 如果Trae显示了我的代码诊断，请告诉我具体内容
- 我可以根据诊断结果进行修复
- 或者我们可以直接开始协同开发
"""
        
        report_path = WORKSPACE / "trae_diagnosis_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"📋 诊断报告已生成: {report_path}")
        print("\n现在你可以:")
        print("  1. 查看截图文件了解Trae界面")
        print("  2. 阅读OCR结果查看文字内容")
        print("  3. 根据诊断报告进行下一步操作")
        
        return True
        
    except Exception as e:
        print(f"❌ Trae诊断检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """主函数"""
    print("开始检查Trae的诊断结果...")
    print(f"时间: 2026-03-07 12:51")
    print(f"工作区: {WORKSPACE}")
    print()
    
    success = await check_trae_diagnosis()
    
    if success:
        print("\n🎉 Trae诊断检查完成！")
        print("\n现在我可以:")
        print("  1. 查看Trae对我的代码诊断")
        print("  2. 根据诊断结果进行修复")
        print("  3. 与Trae协同开发")
        print("  4. 模拟鼠标操作浏览Trae界面")
    else:
        print("\n⚠️ Trae诊断检查失败，需要手动检查")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)