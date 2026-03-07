#!/usr/bin/env python3
"""
GitHub技能管理器配置工具
安全地管理token和配置
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet


class SecureConfigManager:
    """安全配置管理器"""
    
    def __init__(self, config_dir: str = ".kylopro-nexus/config"):
        """
        初始化安全配置管理器
        
        Args:
            config_dir: 配置目录
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 密钥文件路径
        self.key_file = self.config_dir / "encryption.key"
        self.config_file = self.config_dir / "github_skills.json"
        
        # 加载或生成加密密钥
        self.cipher = self._get_cipher()
    
    def _get_cipher(self) -> Optional[Fernet]:
        """获取加密器"""
        try:
            if self.key_file.exists():
                # 加载现有密钥
                key = self.key_file.read_bytes()
            else:
                # 生成新密钥
                key = Fernet.generate_key()
                self.key_file.write_bytes(key)
                print(f"🔑 生成新加密密钥: {self.key_file}")
            
            return Fernet(key)
            
        except Exception as e:
            print(f"⚠️ 加密初始化失败: {e}")
            return None
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        安全保存配置
        
        Args:
            config: 配置字典
            
        Returns:
            是否保存成功
        """
        try:
            # 序列化配置
            config_json = json.dumps(config, ensure_ascii=False, indent=2)
            
            if self.cipher:
                # 加密配置
                encrypted = self.cipher.encrypt(config_json.encode())
                self.config_file.write_bytes(encrypted)
                print(f"✅ 配置已加密保存: {self.config_file}")
            else:
                # 未加密保存（不推荐）
                self.config_file.write_text(config_json, encoding="utf-8")
                print(f"⚠️ 配置未加密保存: {self.config_file}")
            
            return True
            
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
            return False
    
    def load_config(self) -> Optional[Dict[str, Any]]:
        """
        加载配置
        
        Returns:
            配置字典或None
        """
        if not self.config_file.exists():
            print(f"⚠️ 配置文件不存在: {self.config_file}")
            return None
        
        try:
            if self.cipher:
                # 解密配置
                encrypted = self.config_file.read_bytes()
                decrypted = self.cipher.decrypt(encrypted)
                config = json.loads(decrypted.decode())
            else:
                # 加载未加密配置
                config = json.loads(self.config_file.read_text(encoding="utf-8"))
            
            print(f"✅ 配置加载成功: {self.config_file}")
            return config
            
        except Exception as e:
            print(f"❌ 加载配置失败: {e}")
            return None
    
    def get_token(self, token_name: str = "github_skill_token") -> Optional[str]:
        """
        安全获取token
        
        Args:
            token_name: token名称
            
        Returns:
            token字符串或None
        """
        # 优先级1: 环境变量
        env_token = os.getenv(token_name.upper())
        if env_token:
            print(f"✅ 从环境变量获取token: {token_name.upper()}")
            return env_token
        
        # 优先级2: 配置文件
        config = self.load_config()
        if config and token_name in config:
            print(f"✅ 从配置文件获取token: {token_name}")
            return config[token_name]
        
        # 优先级3: 用户输入
        print(f"⚠️ 未找到token: {token_name}")
        return None
    
    def setup_from_desktop_file(self, desktop_file: str = "Kylo技能进化.txt") -> bool:
        """
        从桌面文件设置配置
        
        Args:
            desktop_file: 桌面文件名
            
        Returns:
            是否设置成功
        """
        desktop_path = Path.home() / "Desktop" / desktop_file
        
        if not desktop_path.exists():
            print(f"❌ 桌面文件不存在: {desktop_path}")
            return False
        
        try:
            content = desktop_path.read_text(encoding="utf-8")
            
            # 提取token（简单正则匹配）
            import re
            
            # 查找GitHub token
            tokens = re.findall(r'ghp_[a-zA-Z0-9]+', content)
            if not tokens:
                print("❌ 未在文件中找到GitHub token")
                return False
            
            # 使用最后一个token（假设是最新的）
            github_token = tokens[-1]
            
            # 提取仓库信息
            repo_owner_match = re.search(r'REPO_OWNER\s*=\s*["\']([^"\']+)["\']', content)
            repo_name_match = re.search(r'REPO_NAME\s*=\s*["\']([^"\']+)["\']', content)
            
            repo_owner = repo_owner_match.group(1) if repo_owner_match else "kyloqchen0858"
            repo_name = repo_name_match.group(1) if repo_name_match else "Kylopro-Skills-Repo"
            
            # 创建配置
            config = {
                "github_skill_token": github_token,
                "github_skill_owner": repo_owner,
                "github_skill_repo": repo_name,
                "local_skills_dir": ".kylopro-nexus/skills",
                "setup_from": str(desktop_path),
                "setup_time": os.path.getmtime(str(desktop_path)),
            }
            
            # 保存配置
            success = self.save_config(config)
            
            if success:
                print(f"✅ 从桌面文件设置配置成功")
                print(f"   Token: {github_token[:8]}...{github_token[-4:]}")
                print(f"   仓库: {repo_owner}/{repo_name}")
                return True
            else:
                print("❌ 保存配置失败")
                return False
                
        except Exception as e:
            print(f"❌ 设置配置失败: {e}")
            return False


def setup_secure_config():
    """设置安全配置"""
    print("设置GitHub技能管理器安全配置")
    print("="*60)
    
    config_manager = SecureConfigManager()
    
    # 尝试从桌面文件设置
    print("\n1. 尝试从桌面文件设置配置...")
    if config_manager.setup_from_desktop_file():
        print("✅ 配置设置成功")
    else:
        print("⚠️ 无法从桌面文件设置配置")
        
        # 手动设置选项
        print("\n2. 请选择配置方式:")
        print("   a) 手动输入配置")
        print("   b) 设置环境变量")
        print("   c) 跳过配置")
        
        choice = input("选择 (a/b/c): ").strip().lower()
        
        if choice == "a":
            # 手动输入
            token = input("GitHub Token: ").strip()
            owner = input("仓库所有者 [kyloqchen0858]: ").strip() or "kyloqchen0858"
            repo = input("仓库名称 [Kylopro-Skills-Repo]: ").strip() or "Kylopro-Skills-Repo"
            
            config = {
                "github_skill_token": token,
                "github_skill_owner": owner,
                "github_skill_repo": repo,
                "local_skills_dir": ".kylopro-nexus/skills",
            }
            
            if config_manager.save_config(config):
                print("✅ 手动配置保存成功")
            else:
                print("❌ 手动配置保存失败")
        
        elif choice == "b":
            print("\n请设置以下环境变量:")
            print("  export GITHUB_SKILL_TOKEN='your_token_here'")
            print("  export GITHUB_SKILL_OWNER='kyloqchen0858'")
            print("  export GITHUB_SKILL_REPO='Kylopro-Skills-Repo'")
            print("  export LOCAL_SKILLS_DIR='.kylopro-nexus/skills'")
            print("\n或者在Windows中:")
            print("  setx GITHUB_SKILL_TOKEN your_token_here")
        
        elif choice == "c":
            print("⚠️ 跳过配置，部分功能可能无法使用")
    
    # 测试配置
    print("\n3. 测试配置...")
    token = config_manager.get_token()
    
    if token:
        print(f"✅ Token获取成功: {token[:8]}...{token[-4:]}")
        
        # 显示配置信息
        config = config_manager.load_config()
        if config:
            print("\n当前配置:")
            for key, value in config.items():
                if "token" in key.lower() and isinstance(value, str) and len(value) > 8:
                    print(f"  {key}: {value[:8]}...{value[-4:]}")
                else:
                    print(f"  {key}: {value}")
    else:
        print("❌ 未找到有效token")
    
    print("\n" + "="*60)
    print("配置设置完成!")
    
    return config_manager


if __name__ == "__main__":
    setup_secure_config()