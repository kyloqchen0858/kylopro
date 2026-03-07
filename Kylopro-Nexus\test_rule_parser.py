#!/usr/bin/env python3
"""
测试规则解析器（不依赖LLM）
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def test_rule_parser():
    """测试规则解析器"""
    try:
        print("测试规则解析器...")
        
        # 直接导入规则解析函数
        from skills.task_inbox.parser import _rule_based_parse, _infer_action
        
        # 测试内容
        content = """# 测试任务：IDE桥接器功能验证

## 需求描述
测试Kylopro的IDE桥接器功能，验证是否能与Antigravity协同工作。

## 具体任务
1. **创建测试文件** - 在项目根目录创建test_antigravity.py
2. **编写测试代码** - 测试Antigravity命令行调用
3. **验证连通性** - 检查Antigravity是否响应
4. **生成报告** - 创建测试结果报告

## 技术细节
- 使用Python脚本调用Antigravity
- 验证文件读写功能
- 测试命令执行能力

## 预期结果
- 成功创建测试文件
- Antigravity正确响应
- 生成详细测试报告

## 优先级
高 - 这是后续开发的基础"""
        
        result = _rule_based_parse(content)
        
        print(f"解析结果:")
        print(f"  标题: {result.get('title')}")
        print(f"  摘要: {result.get('summary')}")
        print(f"  子任务数: {len(result.get('subtasks', []))}")
        
        for task in result.get('subtasks', []):
            print(f"  - [{task['id']}] {task['action']}: {task['detail'][:50]}...")
        
        print("✅ 规则解析器测试完成！")
        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_rule_parser()