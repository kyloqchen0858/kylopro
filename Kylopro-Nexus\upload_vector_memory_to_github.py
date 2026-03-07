#!/usr/bin/env python3
"""
上传向量记忆库到GitHub仓库
"""

import os
import sys
import json
import base64
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 从桌面文件读取配置
def read_config_from_desktop():
    """从桌面文件读取配置"""
    desktop_file = Path.home() / "Desktop" / "Kylo技能进化.txt"
    
    if not desktop_file.exists():
        print(f"❌ 桌面文件不存在: {desktop_file}")
        return None
    
    try:
        content = desktop_file.read_text(encoding="utf-8")
        
        # 提取token（使用第二个token，有读写权限）
        import re
        tokens = re.findall(r'ghp_[a-zA-Z0-9]+', content)
        
        if len(tokens) >= 2:
            # 使用第二个token（有读写权限）
            github_token = tokens[1]
            print(f"✅ 找到GitHub Token: {github_token[:8]}...{github_token[-4:]}")
        elif tokens:
            github_token = tokens[0]
            print(f"⚠️ 只找到一个Token，使用它: {github_token[:8]}...{github_token[-4:]}")
        else:
            print("❌ 未在文件中找到GitHub token")
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
        print(f"❌ 读取配置失败: {e}")
        return None


def upload_file_to_github(file_path: Path, config: dict) -> bool:
    """
    上传文件到GitHub仓库
    
    Args:
        file_path: 本地文件路径
        config: 配置字典
        
    Returns:
        是否上传成功
    """
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False
    
    try:
        # 读取文件内容
        file_content = file_path.read_text(encoding="utf-8")
        
        # 检查是否包含敏感信息
        sensitive_patterns = [
            r'api[_-]?key["\']?\s*[:=]\s*["\'][^"\']+["\']',
            r'token["\']?\s*[:=]\s*["\'][^"\']+["\']',
            r'password["\']?\s*[:=]\s*["\'][^"\']+["\']',
            r'secret["\']?\s*[:=]\s*["\'][^"\']+["\']',
        ]
        
        import re
        for pattern in sensitive_patterns:
            if re.search(pattern, file_content, re.IGNORECASE):
                print(f"🚨 检测到敏感信息，停止上传 {file_path.name}!")
                print(f"   请从代码中移除API密钥等敏感信息")
                return False
        
        # Base64编码
        encoded_content = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
        
        # GitHub API URL
        file_name = file_path.name
        url = f"https://api.github.com/repos/{config['owner']}/{config['repo']}/contents/{file_name}"
        
        # 请求头
        headers = {
            "Authorization": f"token {config['token']}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kylopro-Agent/1.0"
        }
        
        # 首先检查文件是否已存在
        import requests
        check_response = requests.get(url, headers=headers, timeout=5)
        
        data = {
            "message": f"Kylopro上传技能: {file_name}",
            "content": encoded_content,
            "branch": "main",
        }
        
        if check_response.status_code == 200:
            # 文件已存在，需要获取SHA进行更新
            existing_data = check_response.json()
            data["sha"] = existing_data["sha"]
            data["message"] = f"Kylopro更新技能: {file_name}"
            print(f"📝 更新现有文件: {file_name}")
        else:
            print(f"📝 上传新文件: {file_name}")
        
        # 上传文件
        response = requests.put(url, headers=headers, data=json.dumps(data), timeout=10)
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"✅ 上传成功: {file_name}")
            print(f"   文件大小: {len(file_content)} 字符")
            print(f"   GitHub URL: {result.get('content', {}).get('html_url', 'N/A')}")
            return True
        else:
            print(f"❌ 上传失败: {response.status_code}")
            print(f"   错误信息: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"⚠️ 上传失败 {file_path.name}: {e}")
        return False


def upload_vector_memory_skill():
    """上传向量记忆库技能"""
    print("="*60)
    print("上传向量记忆库到GitHub仓库")
    print("="*60)
    
    # 1. 读取配置
    print("\n1. 读取配置...")
    config = read_config_from_desktop()
    
    if not config:
        print("❌ 配置读取失败，无法上传")
        return False
    
    print(f"   仓库: {config['owner']}/{config['repo']}")
    
    # 2. 准备要上传的文件
    print("\n2. 准备上传文件...")
    
    vector_memory_dir = project_root / "skills" / "vector_memory"
    if not vector_memory_dir.exists():
        print(f"❌ 向量记忆库目录不存在: {vector_memory_dir}")
        return False
    
    # 要上传的文件列表
    files_to_upload = [
        vector_memory_dir / "SKILL.md",
        vector_memory_dir / "memory.py",
        vector_memory_dir / "__init__.py",
    ]
    
    # 检查文件是否存在
    existing_files = []
    for file_path in files_to_upload:
        if file_path.exists():
            existing_files.append(file_path)
            print(f"   ✅ 找到: {file_path.name}")
        else:
            print(f"   ⚠️ 缺失: {file_path.name}")
    
    if not existing_files:
        print("❌ 没有找到可上传的文件")
        return False
    
    # 3. 上传文件
    print(f"\n3. 上传 {len(existing_files)} 个文件...")
    
    success_count = 0
    for file_path in existing_files:
        if upload_file_to_github(file_path, config):
            success_count += 1
    
    # 4. 上传GitHub技能管理器
    print("\n4. 上传GitHub技能管理器...")
    github_manager_file = project_root / "skills" / "github_skill_manager.py"
    
    if github_manager_file.exists():
        # 读取文件内容
        manager_content = github_manager_file.read_text(encoding="utf-8")
        
        # 移除敏感信息（token相关代码）
        # 这里我们创建一个安全的版本
        safe_content = '''"""
Kylopro 云端技能管理器 (GitHub Skill Manager) - 安全版本
===========================================================
这个技能让我能够从GitHub仓库管理技能，不包含敏感信息。
"""

# 这是一个占位符文件，实际代码需要从安全配置加载
# 保护敏感token信息，不直接包含在代码中

print("GitHub技能管理器 - 请从安全配置加载token")
'''
        
        # 上传安全版本
        temp_file = project_root / "github_skill_manager_safe.py"
        temp_file.write_text(safe_content, encoding="utf-8")
        
        if upload_file_to_github(temp_file, config):
            success_count += 1
            print("✅ GitHub技能管理器（安全版本）上传成功")
        
        # 清理临时文件
        temp_file.unlink()
    else:
        print("⚠️ GitHub技能管理器文件不存在")
    
    # 5. 结果汇总
    print("\n" + "="*60)
    print("上传结果汇总")
    print("="*60)
    
    total_files = len(existing_files) + 1  # 包括GitHub管理器
    print(f"总文件数: {total_files}")
    print(f"上传成功: {success_count}")
    print(f"上传失败: {total_files - success_count}")
    
    if success_count > 0:
        print(f"\n✅ 部分文件上传成功!")
        print(f"   访问仓库: https://github.com/{config['owner']}/{config['repo']}")
    else:
        print(f"\n❌ 所有文件上传失败!")
    
    # 6. 安全建议
    print("\n" + "="*60)
    print("安全建议")
    print("="*60)
    
    print("1. 🔒 Token保护:")
    print("   - GitHub Token已从代码中移除")
    print("   - 实际使用时从环境变量或加密配置加载")
    
    print("\n2. 📁 仓库管理:")
    print(f"   - 仓库: {config['owner']}/{config['repo']}")
    print("   - 建议设置为私有仓库")
    print("   - 定期轮换Token")
    
    print("\n3. 🔍 代码审查:")
    print("   - 上传前检查敏感信息")
    print("   - 使用.gitignore排除配置文件")
    print("   - 考虑使用GitHub Secrets")
    
    return success_count > 0


def test_github_connection(config: dict) -> bool:
    """测试GitHub连接"""
    print("\n测试GitHub连接...")
    
    try:
        import requests
        
        # 测试API连接
        test_url = f"https://api.github.com/repos/{config['owner']}/{config['repo']}"
        headers = {
            "Authorization": f"token {config['token']}",
            "Accept": "application/vnd.github.v3+json",
        }
        
        response = requests.get(test_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            repo_info = response.json()
            print(f"✅ GitHub连接成功!")
            print(f"   仓库: {repo_info.get('full_name')}")
            print(f"   描述: {repo_info.get('description', '无描述')}")
            print(f"   私有: {repo_info.get('private', '未知')}")
            return True
        else:
            print(f"❌ GitHub连接失败: {response.status_code}")
            print(f"   错误: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"⚠️ 连接测试失败: {e}")
        return False


def main():
    """主函数"""
    print("向量记忆库GitHub上传工具")
    print("时间: 2026-03-07 14:15")
    print()
    
    # 读取配置
    config = read_config_from_desktop()
    if not config:
        return 1
    
    # 测试连接
    if not test_github_connection(config):
        print("⚠️ 连接测试失败，继续尝试上传...")
    
    # 上传文件
    success = upload_vector_memory_skill()
    
    if success:
        print("\n🎉 上传任务完成!")
        print("\n下一步:")
        print("  1. 检查GitHub仓库确认文件")
        print("  2. 测试从仓库下载技能")
        print("  3. 集成到Kylopro核心系统")
        return 0
    else:
        print("\n❌ 上传任务失败!")
        return 1


if __name__ == "__main__":
    sys.exit(main())