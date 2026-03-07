#!/usr/bin/env python3
"""
验证文件是否上传成功
"""

import requests
import re
from pathlib import Path

def verify_upload():
    """验证上传"""
    print("验证文件上传...")
    
    # 从桌面文件读取token
    desktop_file = Path.home() / "Desktop" / "Kylo技能进化.txt"
    
    if not desktop_file.exists():
        print("ERROR: 桌面文件不存在")
        return False
    
    try:
        content = desktop_file.read_text(encoding="utf-8")
        tokens = re.findall(r'ghp_[a-zA-Z0-9]+', content)
        
        if not tokens:
            print("ERROR: 未找到token")
            return False
        
        github_token = tokens[-1]
        
        # 仓库信息
        repo_owner = "kyloqchen0858"
        repo_name = "Kylopro-Skills-Repo"
        file_name = "current_session_context.md"
        
        # API URL
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_name}"
        
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        # 获取文件信息
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            file_info = response.json()
            
            print("SUCCESS: 文件上传验证成功!")
            print(f"   文件名: {file_info.get('name')}")
            print(f"   文件大小: {file_info.get('size')} 字节")
            print(f"   SHA: {file_info.get('sha')[:8]}...")
            print(f"   下载URL: {file_info.get('download_url')}")
            print(f"   GitHub URL: {file_info.get('html_url')}")
            
            # 下载并显示部分内容
            download_url = file_info.get('download_url')
            if download_url:
                content_response = requests.get(download_url, timeout=10)
                if content_response.status_code == 200:
                    content = content_response.text
                    print(f"\n文件内容预览:")
                    print("-" * 60)
                    lines = content.split('\n')[:10]
                    for line in lines:
                        print(f"  {line}")
                    print("-" * 60)
            
            return True
        else:
            print(f"ERROR: 文件不存在或无法访问: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR: 验证失败: {e}")
        return False

if __name__ == "__main__":
    success = verify_upload()
    
    if success:
        print("\n" + "="*60)
        print("验证完成!")
        print("\n用户可以访问:")
        print("  https://github.com/kyloqchen0858/Kylopro-Skills-Repo/blob/main/current_session_context.md")
        print("\n检查文档内容，了解当前会话状态和问题。")
    else:
        print("\n验证失败，请手动检查GitHub仓库。")