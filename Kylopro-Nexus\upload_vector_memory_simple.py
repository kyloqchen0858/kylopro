#!/usr/bin/env python3
"""
简单版本：上传向量记忆库到GitHub
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

def read_config():
    """读取配置"""
    desktop_file = Path.home() / "Desktop" / "Kylo技能进化.txt"
    
    if not desktop_file.exists():
        print("ERROR: 桌面文件不存在")
        return None
    
    try:
        content = desktop_file.read_text(encoding="utf-8")
        
        # 提取token
        tokens = re.findall(r'ghp_[a-zA-Z0-9]+', content)
        
        if len(tokens) >= 2:
            github_token = tokens[1]
            print(f"INFO: 找到GitHub Token: {github_token[:8]}...{github_token[-4:]}")
        elif tokens:
            github_token = tokens[0]
            print(f"INFO: 只找到一个Token: {github_token[:8]}...{github_token[-4:]}")
        else:
            print("ERROR: 未找到GitHub token")
            return None
        
        # 提取仓库信息
        repo_owner_match = re.search(r'REPO_OWNER\s*=\s*["\']([^"\']+)["\']', content)
        repo_name_match = re.search(r'REPO_NAME\s*=\s*["\']([^"\']+)["\']', content)
        
        repo_owner = repo_owner_match.group(1) if repo_owner_match else "kyloqchen0858"
        repo_name = repo_name_match.group(1) if repo_name_match else "Kylopro-Skills-Repo"
        
        return {
            "token": github_token,
            "owner": repo_owner,
            "repo": repo_name,
        }
        
    except Exception as e:
        print(f"ERROR: 读取配置失败: {e}")
        return None

def upload_file(file_path, config):
    """上传单个文件"""
    if not file_path.exists():
        print(f"ERROR: 文件不存在: {file_path}")
        return False
    
    try:
        import requests
        
        # 读取文件
        file_content = file_path.read_text(encoding="utf-8")
        
        # 检查敏感信息
        sensitive_patterns = [
            r'api[_-]?key["\']?\s*[:=]\s*["\'][^"\']+["\']',
            r'token["\']?\s*[:=]\s*["\'][^"\']+["\']',
        ]
        
        for pattern in sensitive_patterns:
            if re.search(pattern, file_content, re.IGNORECASE):
                print(f"SECURITY: 检测到敏感信息，跳过 {file_path.name}")
                return False
        
        # Base64编码
        encoded_content = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
        
        # API URL
        file_name = file_path.name
        url = f"https://api.github.com/repos/{config['owner']}/{config['repo']}/contents/{file_name}"
        
        # 请求头
        headers = {
            "Authorization": f"token {config['token']}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kylopro-Agent"
        }
        
        # 检查文件是否已存在
        try:
            check_response = requests.get(url, headers=headers, timeout=5)
            if check_response.status_code == 200:
                # 更新现有文件
                existing_data = check_response.json()
                data = {
                    "message": f"更新: {file_name}",
                    "content": encoded_content,
                    "sha": existing_data["sha"],
                    "branch": "main",
                }
                print(f"INFO: 更新文件: {file_name}")
            else:
                # 上传新文件
                data = {
                    "message": f"上传: {file_name}",
                    "content": encoded_content,
                    "branch": "main",
                }
                print(f"INFO: 上传新文件: {file_name}")
        except:
            # 上传新文件
            data = {
                "message": f"上传: {file_name}",
                "content": encoded_content,
                "branch": "main",
            }
            print(f"INFO: 上传新文件: {file_name}")
        
        # 上传
        response = requests.put(url, headers=headers, data=json.dumps(data), timeout=10)
        
        if response.status_code in [200, 201]:
            print(f"SUCCESS: 上传成功: {file_name}")
            return True
        else:
            print(f"ERROR: 上传失败 {file_name}: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"ERROR: 上传失败 {file_path.name}: {e}")
        return False

def main():
    """主函数"""
    print("开始上传向量记忆库到GitHub...")
    
    # 读取配置
    config = read_config()
    if not config:
        print("ERROR: 配置读取失败")
        return 1
    
    print(f"INFO: 仓库: {config['owner']}/{config['repo']}")
    
    # 要上传的文件
    vector_memory_dir = project_root / "skills" / "vector_memory"
    files_to_upload = [
        vector_memory_dir / "SKILL.md",
        vector_memory_dir / "memory.py",
        vector_memory_dir / "__init__.py",
    ]
    
    # 检查文件
    existing_files = []
    for file_path in files_to_upload:
        if file_path.exists():
            existing_files.append(file_path)
            print(f"INFO: 找到文件: {file_path.name}")
        else:
            print(f"WARNING: 文件不存在: {file_path.name}")
    
    if not existing_files:
        print("ERROR: 没有可上传的文件")
        return 1
    
    # 上传文件
    print(f"\n开始上传 {len(existing_files)} 个文件...")
    success_count = 0
    
    for file_path in existing_files:
        if upload_file(file_path, config):
            success_count += 1
    
    # 结果
    print(f"\n上传完成!")
    print(f"总文件数: {len(existing_files)}")
    print(f"成功: {success_count}")
    print(f"失败: {len(existing_files) - success_count}")
    
    if success_count > 0:
        print(f"\nSUCCESS: 文件已上传到GitHub!")
        print(f"仓库地址: https://github.com/{config['owner']}/{config['repo']}")
        return 0
    else:
        print("\nERROR: 所有文件上传失败!")
        return 1

if __name__ == "__main__":
    sys.exit(main())