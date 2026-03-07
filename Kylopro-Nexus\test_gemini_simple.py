#!/usr/bin/env python3
"""
简单测试Gemini API
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

async def test_gemini_direct():
    """直接测试Gemini API"""
    print("直接测试Gemini API...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ 未找到GEMINI_API_KEY")
        return False
    
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    
    # 尝试不同的API端点
    endpoints = [
        "https://generativelanguage.googleapis.com/v1beta",
        "https://generativelanguage.googleapis.com/v1",
    ]
    
    for base_url in endpoints:
        print(f"\n尝试端点: {base_url}")
        
        try:
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
            )
            
            # 尝试获取模型列表
            models = await client.models.list()
            print(f"✅ 连接成功!")
            print(f"   可用模型: {len(models.data)} 个")
            
            # 显示前几个模型
            for model in models.data[:3]:
                print(f"   - {model.id}")
            
            # 测试对话
            print("\n测试对话...")
            response = await client.chat.completions.create(
                model="gemini-1.5-flash",
                messages=[
                    {"role": "user", "content": "用一句话回复'测试成功'"}
                ],
                max_tokens=50,
            )
            
            content = response.choices[0].message.content
            print(f"✅ 对话测试成功!")
            print(f"   回复: {content}")
            
            return True
            
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            continue
    
    return False


async def test_gemini_vision():
    """测试Gemini视觉功能"""
    print("\n测试Gemini视觉功能...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False
    
    try:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta",
        )
        
        # 测试多模态消息
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图片里有什么？"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
                        }
                    }
                ]
            }
        ]
        
        print("发送图片分析请求...")
        response = await client.chat.completions.create(
            model="gemini-1.5-flash",
            messages=messages,
            max_tokens=100,
        )
        
        content = response.choices[0].message.content
        print(f"✅ 视觉分析成功!")
        print(f"   分析结果: {content}")
        
        return True
        
    except Exception as e:
        print(f"❌ 视觉分析失败: {e}")
        return False


async def main():
    """主函数"""
    print("Gemini API测试")
    print("="*60)
    
    # 测试直接连接
    success = await test_gemini_direct()
    
    if success:
        # 测试视觉功能
        await test_gemini_vision()
        
        print("\n" + "="*60)
        print("🎉 Gemini API测试成功!")
        print("\n现在可以:")
        print("  1. 使用Gemini进行文本对话")
        print("  2. 使用Gemini进行图片分析")
        print("  3. 集成到Kylopro视觉路由")
        return 0
    else:
        print("\n" + "="*60)
        print("❌ Gemini API测试失败")
        print("\n可能的原因:")
        print("  1. API Key无效")
        print("  2. API端点不正确")
        print("  3. 网络连接问题")
        print("  4. 免费额度已用完")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))