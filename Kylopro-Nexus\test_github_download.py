#!/usr/bin/env python3
"""
测试从GitHub下载刚刚上传的文件
"""

import requests
import base64
import re
from pathlib import Path

def test_download():
    """测试下载"""
    print("测试从GitHub下载文件...")
    
    # 从桌面文件读取配置
    desktop_file = Path.home() / "Desktop" / "Kylo技能进化.txt"
    
    if not desktop_file.exists():
        print("ERROR: 桌面文件不存在")
        return False
    
    try:
        content = desktop_file.read_text(encoding="utf-8")
        
        # 提取token
        tokens = re.findall(r'ghp_[a-zA-Z0-9]+', content)
        if not tokens:
            print("ERROR: 未找到token")
            return False
        
        github_token = tokens[-1]  # 使用最后一个token
        print(f"INFO: 使用Token: {github_token[:8]}...{github_token[-4:]}")
        
        # 仓库信息
        repo_owner = "kyloqchen0858"
        repo_name = "Kylopro-Skills-Repo"
        
        # 要下载的文件
        files_to_download = ["memory.py", "__init__.py"]
        
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        for file_name in files_to_download:
            print(f"\n下载: {file_name}")
            
            url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_name}"
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    file_data = response.json()
                    
                    if file_data["encoding"] == "base64":
                        # 解码内容
                        file_content = base64.b64decode(file_data["content"]).decode("utf-8")
                        
                        print(f"SUCCESS: 下载成功!")
                        print(f"  文件大小: {len(file_content)} 字符")
                        print(f"  SHA: {file_data['sha'][:8]}...")
                        print(f"  下载URL: {file_data['download_url']}")
                        
                        # 保存到本地测试
                        test_dir = Path("test_download")
                        test_dir.mkdir(exist_ok=True)
                        
                        test_file = test_dir / file_name
                        test_file.write_text(file_content, encoding="utf-8")
                        print(f"  保存到: {test_file}")
                        
                    else:
                        print(f"ERROR: 不支持的编码: {file_data.get('encoding')}")
                        
                else:
                    print(f"ERROR: 下载失败: {response.status_code}")
                    print(f"  错误: {response.text[:100]}")
                    
            except Exception as e:
                print(f"ERROR: 下载异常: {e}")
        
        print("\n" + "="*60)
        print("下载测试完成!")
        print(f"仓库地址: https://github.com/{repo_owner}/{repo_name}")
        print("可以访问仓库查看上传的文件")
        
        return True
        
    except Exception as e:
        print(f"ERROR: 测试失败: {e}")
        return False

if __name__ == "__main__":
    test_download()