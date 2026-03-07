#!/usr/bin/env python3
"""
上传当前会话文档到 kylo_autoagent 仓库
"""

import os
import sys
import json
import base64
import re
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def read_github_token():
    """读取GitHub Token"""
    desktop_file = Path.home() / "Desktop" / "Kylo技能进化.txt"
    
    if not desktop_file.exists():
        print("ERROR: 桌面文件不存在")
        return None
    
    try:
        content = desktop_file.read_text(encoding="utf-8")
        
        # 提取token（使用第二个token，有读写权限）
        tokens = re.findall(r'ghp_[a-zA-Z0-9]+', content)
        
        if len(tokens) >= 2:
            github_token = tokens[1]
            print(f"INFO: 使用GitHub Token: {github_token[:8]}...{github_token[-4:]}")
            return github_token
        elif tokens:
            github_token = tokens[0]
            print(f"WARNING: 只找到一个Token: {github_token[:8]}...{github_token[-4:]}")
            return github_token
        else:
            print("ERROR: 未找到GitHub token")
            return None
            
    except Exception as e:
        print(f"ERROR: 读取token失败: {e}")
        return None

def upload_to_github(file_path, repo_owner, repo_name, github_token):
    """上传文件到GitHub"""
    if not file_path.exists():
        print(f"ERROR: 文件不存在: {file_path}")
        return False
    
    try:
        import requests
        
        # 读取文件内容
        file_content = file_path.read_text(encoding="utf-8")
        file_name = file_path.name
        
        # Base64编码
        encoded_content = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
        
        # GitHub API URL
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/{file_name}"
        
        # 请求头
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kylopro-Agent"
        }
        
        # 提交消息
        commit_message = f"Kylopro上传会话文档: {file_name}"
        
        # 准备数据
        data = {
            "message": commit_message,
            "content": encoded_content,
            "branch": "main",
        }
        
        # 首先检查文件是否已存在
        try:
            check_response = requests.get(url, headers=headers, timeout=5)
            if check_response.status_code == 200:
                # 更新现有文件
                existing_data = check_response.json()
                data["sha"] = existing_data["sha"]
                data["message"] = f"Kylopro更新会话文档: {file_name}"
                print(f"INFO: 更新现有文件: {file_name}")
            else:
                print(f"INFO: 上传新文件: {file_name}")
        except:
            print(f"INFO: 上传新文件: {file_name}")
        
        # 上传文件
        response = requests.put(url, headers=headers, data=json.dumps(data), timeout=10)
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"SUCCESS: 上传成功: {file_name}")
            print(f"   文件大小: {len(file_content)} 字符")
            print(f"   GitHub URL: {result.get('content', {}).get('html_url', 'N/A')}")
            print(f"   提交SHA: {result.get('commit', {}).get('sha', 'N/A')[:8]}...")
            return True
        else:
            print(f"ERROR: 上传失败: {response.status_code}")
            print(f"   错误: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"ERROR: 上传失败: {e}")
        return False

def check_repo_exists(repo_owner, repo_name, github_token):
    """检查仓库是否存在"""
    try:
        import requests
        
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
        headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            repo_info = response.json()
            print(f"INFO: 仓库存在: {repo_info.get('full_name')}")
            print(f"   描述: {repo_info.get('description', '无描述')}")
            print(f"   私有: {repo_info.get('private', '未知')}")
            print(f"   星标: {repo_info.get('stargazers_count', 0)}")
            return True
        elif response.status_code == 404:
            print(f"WARNING: 仓库不存在: {repo_owner}/{repo_name}")
            print(f"   错误: 404 - 仓库未找到")
            return False
        else:
            print(f"ERROR: 检查仓库失败: {response.status_code}")
            print(f"   错误: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"ERROR: 检查仓库失败: {e}")
        return False

def main():
    """主函数"""
    print("上传当前会话文档到 kylo_autoagent 仓库")
    print("="*60)
    
    # 读取GitHub Token
    github_token = read_github_token()
    if not github_token:
        print("ERROR: 无法获取GitHub Token")
        return 1
    
    # 仓库信息
    repo_owner = "kyloqchen0858"
    repo_name = "kylo_autoagent"  # 用户指定的仓库
    
    print(f"\n目标仓库: {repo_owner}/{repo_name}")
    
    # 检查仓库是否存在
    print("\n检查仓库是否存在...")
    if not check_repo_exists(repo_owner, repo_name, github_token):
        print(f"\nWARNING: 仓库 {repo_name} 可能不存在")
        print("尝试上传到 Kylopro-Skills-Repo 作为备用")
        repo_name = "Kylopro-Skills-Repo"
    
    # 要上传的文件
    file_to_upload = project_root / "current_session_context.md"
    
    if not file_to_upload.exists():
        print(f"ERROR: 要上传的文件不存在: {file_to_upload}")
        return 1
    
    print(f"\n上传文件: {file_to_upload.name}")
    print(f"文件大小: {file_to_upload.stat().st_size} 字节")
    
    # 上传文件
    print(f"\n开始上传到 {repo_owner}/{repo_name}...")
    success = upload_to_github(file_to_upload, repo_owner, repo_name, github_token)
    
    # 结果
    print("\n" + "="*60)
    if success:
        print("🎉 上传成功!")
        print(f"\n文档已上传到: https://github.com/{repo_owner}/{repo_name}")
        print(f"文件: current_session_context.md")
        print("\n用户可以:")
        print("  1. 访问GitHub仓库查看文档")
        print("  2. 检查项目状态和问题")
        print("  3. 提供反馈和下一步指导")
        return 0
    else:
        print("❌ 上传失败!")
        print("\n可能的原因:")
        print("  1. 仓库不存在或无权访问")
        print("  2. Token权限不足")
        print("  3. 网络连接问题")
        print("  4. 文件内容有问题")
        return 1

if __name__ == "__main__":
    sys.exit(main())