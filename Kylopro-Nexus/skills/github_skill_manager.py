#!/usr/bin/env python3
"""
Kylopro 云端技能管理器 (GitHub Skill Manager)
===============================================
这个技能让我能够：
1. 从GitHub仓库搜索和下载技能
2. 动态加载技能到内存（热加载）
3. 上传自己开发的技能到GitHub
4. 管理云端技能库

安全注意事项：
- 保护敏感token信息
- 不要上传API密钥
- 验证代码安全性

Windows 路径注意事项：
- 所有传给 git 命令的路径需要用正斜杠（/），不能用反斜杠（\\）
- 使用 _normalize_path() 辅助函数转换
"""

import os
import sys
import json
import base64
import importlib.util
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

import requests
from pydantic import BaseModel, Field

# 添加项目根目录到路径（确保可以 import 同级模块）
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 日志（使用标准 logging 或 loguru，两者兼容）
try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


def _normalize_path(path) -> str:
    """
    将路径转换为正斜杠格式，避免 Windows 反斜杠导致 git 路径乱码。

    在 Windows 上，Path 对象的 str() 输出使用反斜杠（\\），
    而 git 命令需要正斜杠（/）。这个函数统一处理这种转换。

    Args:
        path: 字符串路径或 Path 对象

    Returns:
        使用正斜杠的路径字符串
    """
    # 将 Windows 反斜杠路径转换为正斜杠，避免 git 路径乱码
    return str(path).replace("\\", "/")


class GitHubSkillConfig(BaseModel):
    """GitHub技能配置"""
    token: str = Field(description="GitHub个人访问令牌")
    owner: str = Field(default="kyloqchen0858", description="仓库所有者")
    repo: str = Field(default="Kylopro-Skills-Repo", description="仓库名称")
    local_skills_dir: str = Field(default=".kylopro-nexus/skills", description="本地技能目录")
    base_url: str = Field(default="https://api.github.com", description="GitHub API基础URL")

    class Config:
        arbitrary_types_allowed = True


class SkillInfo(BaseModel):
    """技能信息"""
    name: str
    file_path: str
    github_url: str
    local_path: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = "1.0.0"
    dependencies: List[str] = Field(default_factory=list)
    installed: bool = False
    last_updated: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GitHubSkillManager:
    """GitHub技能管理器"""

    def __init__(self, config: Optional[GitHubSkillConfig] = None):
        """
        初始化技能管理器

        Args:
            config: GitHub配置，如果为None则从环境变量加载
        """
        self.config = config or self._load_config_from_env()
        self.headers = {
            "Authorization": f"token {self.config.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Kylopro-Agent/1.0"
        }

        # 仓库根目录（用于 git 命令的 cwd 参数）
        self.repo_path = project_root

        # 确保本地目录存在
        self._setup_local_directory()

        # 配置 git（关闭路径转义，避免中文和特殊字符乱码）
        self._configure_git()

        # 缓存已安装的技能
        self.installed_skills: Dict[str, SkillInfo] = {}
        self.loaded_modules: Dict[str, Any] = {}

        # 统计信息
        self.stats = {
            "total_searches": 0,
            "total_downloads": 0,
            "total_uploads": 0,
            "total_loads": 0,
        }

        print(f"✅ GitHub技能管理器初始化成功")
        print(f"   仓库: {self.config.owner}/{self.config.repo}")
        print(f"   本地目录: {self.config.local_skills_dir}")

    def _configure_git(self):
        """
        配置 git 以避免 Windows 路径乱码问题。

        在 Windows 上，git 默认会对非 ASCII 字符使用 octal 编码，
        设置 core.quotepath=false 后会显示原始字符。
        """
        try:
            # 关闭路径转义（避免中文和特殊字符乱码）
            subprocess.run(
                ["git", "config", "core.quotepath", "false"],
                capture_output=True,
                cwd=self.repo_path
            )
            # Windows 换行符自动转换
            subprocess.run(
                ["git", "config", "core.autocrlf", "true"],
                capture_output=True,
                cwd=self.repo_path
            )
            logger.debug("git 配置已更新（quotepath=false, autocrlf=true）")
        except Exception as e:
            # git 配置失败不影响功能，只记录警告
            logger.warning(f"git 配置失败（不影响功能）: {e}")

    def _load_config_from_env(self) -> GitHubSkillConfig:
        """从环境变量加载配置"""
        # 注意：这里应该从安全的地方加载token，比如环境变量或加密文件
        # 为了安全，我们不会硬编码token

        token = os.getenv("GITHUB_SKILL_TOKEN")
        if not token:
            # 尝试从桌面文件读取（仅用于演示）
            desktop_file = Path.home() / "Desktop" / "Kylo技能进化.txt"
            if desktop_file.exists():
                try:
                    with open(desktop_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        # 简单提取token（实际应该用更安全的方式）
                        import re
                        tokens = re.findall(r'ghp_[a-zA-Z0-9]+', content)
                        if tokens:
                            token = tokens[-1]  # 使用最后一个token
                except Exception:
                    pass

        if not token:
            raise ValueError("未找到GitHub Token。请设置GITHUB_SKILL_TOKEN环境变量")

        return GitHubSkillConfig(
            token=token,
            owner=os.getenv("GITHUB_SKILL_OWNER", "kyloqchen0858"),
            repo=os.getenv("GITHUB_SKILL_REPO", "Kylopro-Skills-Repo"),
            local_skills_dir=os.getenv("LOCAL_SKILLS_DIR", ".kylopro-nexus/skills"),
        )

    def _setup_local_directory(self):
        """设置本地技能目录"""
        local_dir = Path(self.config.local_skills_dir)
        local_dir.mkdir(parents=True, exist_ok=True)

        # 创建__init__.py文件
        init_file = local_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Kylopro Skills Package\n# Auto-generated by GitHub Skill Manager\n")

        print(f"📁 本地技能目录: {local_dir.absolute()}")

    def search_skill(self, skill_name: str, file_ext: str = ".py") -> Optional[SkillInfo]:
        """
        在GitHub仓库中搜索技能

        Args:
            skill_name: 技能名称
            file_ext: 文件扩展名

        Returns:
            SkillInfo对象或None
        """
        print(f"🔍 搜索技能: {skill_name}")
        self.stats["total_searches"] += 1

        # 构造搜索查询
        query = f"{skill_name} in:file extension:{file_ext[1:]} repo:{self.config.owner}/{self.config.repo}"
        search_url = f"{self.config.base_url}/search/code?q={query}"

        try:
            response = requests.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data["total_count"] > 0:
                # 获取第一个匹配文件
                file_info = data["items"][0]

                skill_info = SkillInfo(
                    name=skill_name,
                    file_path=file_info["path"],
                    github_url=file_info["html_url"],
                    description=f"Found in GitHub: {file_info['path']}",
                )

                print(f"✅ 找到技能: {skill_info.file_path}")
                return skill_info
            else:
                print(f"❌ 未找到技能: {skill_name}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"⚠️ 搜索失败: {e}")
            return None

    def download_skill(self, skill_info: SkillInfo) -> Optional[Path]:
        """
        从GitHub下载技能

        Args:
            skill_info: 技能信息

        Returns:
            本地文件路径或None
        """
        print(f"⬇️ 下载技能: {skill_info.name}")

        # 获取文件内容API URL
        content_url = f"{self.config.base_url}/repos/{self.config.owner}/{self.config.repo}/contents/{skill_info.file_path}"

        try:
            response = requests.get(content_url, headers=self.headers, timeout=10)
            response.raise_for_status()

            content_data = response.json()

            if content_data["encoding"] == "base64":
                # 解码Base64内容
                file_content = base64.b64decode(content_data["content"]).decode("utf-8")

                # 确定本地保存路径
                local_dir = Path(self.config.local_skills_dir)
                local_path = local_dir / Path(skill_info.file_path).name

                # 保存文件
                local_path.write_text(file_content, encoding="utf-8")

                # 更新技能信息
                skill_info.local_path = str(local_path)
                skill_info.installed = True
                skill_info.last_updated = datetime.now()

                self.installed_skills[skill_info.name] = skill_info
                self.stats["total_downloads"] += 1

                print(f"✅ 技能下载成功: {local_path}")
                return local_path

            else:
                print(f"❌ 不支持的编码格式: {content_data.get('encoding')}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"⚠️ 下载失败: {e}")
            return None

    def upload_skill(self, skill_name: str, code_content: str,
                     message: Optional[str] = None) -> bool:
        """
        上传技能到GitHub仓库

        Args:
            skill_name: 技能名称
            code_content: 代码内容
            message: 提交消息

        Returns:
            是否上传成功
        """
        print(f"⬆️ 上传技能: {skill_name}")

        # 保护敏感信息 - 检查代码中是否包含API密钥
        sensitive_patterns = [
            r'api[_-]?key["\']?\s*[:=]\s*["\'][^"\']+["\']',
            r'token["\']?\s*[:=]\s*["\'][^"\']+["\']',
            r'password["\']?\s*[:=]\s*["\'][^"\']+["\']',
            r'secret["\']?\s*[:=]\s*["\'][^"\']+["\']',
        ]

        import re
        for pattern in sensitive_patterns:
            if re.search(pattern, code_content, re.IGNORECASE):
                print(f"🚨 检测到敏感信息，停止上传！")
                print(f"   请从代码中移除API密钥等敏感信息")
                return False

        # 准备上传数据
        encoded_content = base64.b64encode(code_content.encode("utf-8")).decode("utf-8")

        upload_url = f"{self.config.base_url}/repos/{self.config.owner}/{self.config.repo}/contents/{skill_name}.py"

        commit_message = message or f"Kylopro自动上传新技能: {skill_name}"

        data = {
            "message": commit_message,
            "content": encoded_content,
            "branch": "main",
        }

        try:
            # 首先检查文件是否已存在
            check_response = requests.get(upload_url, headers=self.headers, timeout=5)

            if check_response.status_code == 200:
                # 文件已存在，需要获取SHA进行更新
                existing_data = check_response.json()
                data["sha"] = existing_data["sha"]
                commit_message = f"Kylopro更新技能: {skill_name}"
                data["message"] = commit_message

            # 上传文件
            response = requests.put(upload_url, headers=self.headers,
                                     data=json.dumps(data), timeout=10)

            if response.status_code in [200, 201]:
                print(f"🎉 技能上传成功: {skill_name}.py")
                print(f"   提交消息: {commit_message}")
                print(f"   GitHub URL: {response.json().get('content', {}).get('html_url', 'N/A')}")

                self.stats["total_uploads"] += 1
                return True
            else:
                print(f"❌ 上传失败: {response.status_code}")
                print(f"   错误信息: {response.text[:200]}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"⚠️ 上传失败: {e}")
            return False

    def git_add(self, path) -> bool:
        """
        将文件添加到 git 暂存区。

        注意：路径会自动转换为正斜杠格式，避免 Windows 路径乱码。

        Args:
            path: 文件路径（支持 Path 对象或字符串）

        Returns:
            是否成功
        """
        # 将 Windows 反斜杠路径转换为正斜杠，避免 git 路径乱码
        path_str = _normalize_path(path)
        try:
            result = subprocess.run(
                ["git", "add", path_str],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            if result.returncode != 0:
                logger.warning(f"git add 失败: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"git add 执行失败: {e}")
            return False

    def git_commit(self, message: str) -> bool:
        """
        提交 git 变更。

        Args:
            message: 提交消息

        Returns:
            是否成功
        """
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            if result.returncode != 0:
                logger.warning(f"git commit 失败: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"git commit 执行失败: {e}")
            return False

    def git_push(self, remote: str = "origin", branch: str = "main") -> bool:
        """
        推送 git 变更到远程仓库。

        Args:
            remote: 远程仓库名（默认 origin）
            branch: 分支名（默认 main）

        Returns:
            是否成功
        """
        try:
            result = subprocess.run(
                ["git", "push", remote, branch],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            if result.returncode != 0:
                logger.warning(f"git push 失败: {result.stderr}")
                return False
            return True
        except Exception as e:
            logger.error(f"git push 执行失败: {e}")
            return False

    def commit_and_push_skill(self, skill_path, commit_message: str) -> bool:
        """
        将技能文件提交并推送到 git 仓库。
        这个方法整合了 git add、commit、push 三步操作。

        Args:
            skill_path: 技能文件路径（会自动转换为正斜杠）
            commit_message: 提交消息

        Returns:
            是否全部成功
        """
        # 将 Windows 反斜杠路径转换为正斜杠，避免 git 路径乱码
        path_str = _normalize_path(skill_path)

        print(f"📤 提交技能到 git: {path_str}")

        # 步骤1：git add（使用正斜杠路径）
        if not self.git_add(path_str):
            print(f"❌ git add 失败")
            return False

        # 步骤2：git commit
        if not self.git_commit(commit_message):
            print(f"❌ git commit 失败")
            return False

        # 步骤3：git push
        if not self.git_push():
            print(f"❌ git push 失败")
            return False

        print(f"✅ 技能已成功提交到 git")
        return True

    def load_skill(self, skill_name: str) -> Optional[Any]:
        """
        动态加载技能模块（热加载）

        Args:
            skill_name: 技能名称

        Returns:
            加载的模块或None
        """
        print(f"🚀 加载技能: {skill_name}")

        # 检查技能是否已安装
        if skill_name not in self.installed_skills:
            print(f"❌ 技能未安装: {skill_name}")
            return None

        skill_info = self.installed_skills[skill_name]

        if not skill_info.local_path or not Path(skill_info.local_path).exists():
            print(f"❌ 技能文件不存在: {skill_info.local_path}")
            return None

        try:
            # 动态加载模块
            spec = importlib.util.spec_from_file_location(skill_name, skill_info.local_path)
            if spec is None:
                print(f"❌ 无法创建模块规范: {skill_name}")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 缓存模块
            self.loaded_modules[skill_name] = module
            self.stats["total_loads"] += 1

            print(f"✅ 技能加载成功: {skill_name}")

            # 检查是否有标准接口
            if hasattr(module, "run"):
                print(f"   检测到标准接口: run()")
            if hasattr(module, "execute"):
                print(f"   检测到标准接口: execute()")
            if hasattr(module, "process"):
                print(f"   检测到标准接口: process()")

            return module

        except Exception as e:
            print(f"💥 加载技能失败: {e}")
            return None

    def run_skill(self, skill_name: str, *args, **kwargs) -> Any:
        """
        运行已加载的技能

        Args:
            skill_name: 技能名称
            *args, **kwargs: 传递给技能的参数

        Returns:
            技能执行结果
        """
        if skill_name not in self.loaded_modules:
            # 尝试先加载
            module = self.load_skill(skill_name)
            if module is None:
                return None

        module = self.loaded_modules[skill_name]

        try:
            # 尝试调用标准接口
            if hasattr(module, "run"):
                return module.run(*args, **kwargs)
            elif hasattr(module, "execute"):
                return module.execute(*args, **kwargs)
            elif hasattr(module, "process"):
                return module.process(*args, **kwargs)
            else:
                print(f"⚠️ 技能 {skill_name} 没有标准接口")
                return None

        except Exception as e:
            print(f"💥 运行技能失败: {e}")
            return None

    def list_installed_skills(self) -> List[SkillInfo]:
        """列出所有已安装的技能"""
        local_dir = Path(self.config.local_skills_dir)

        skills = []
        for file_path in local_dir.glob("*.py"):
            if file_path.name == "__init__.py":
                continue

            skill_name = file_path.stem
            skill_info = SkillInfo(
                name=skill_name,
                file_path=str(file_path),
                github_url="",
                local_path=str(file_path),
                installed=True,
                last_updated=datetime.fromtimestamp(file_path.stat().st_mtime),
            )

            skills.append(skill_info)

        return skills

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "installed_skills_count": len(self.installed_skills),
            "loaded_modules_count": len(self.loaded_modules),
            "local_skills_count": len(self.list_installed_skills()),
        }

    def backup_skills(self, backup_dir: str = "./backups/skills") -> bool:
        """备份所有技能到本地目录"""
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_path / f"skills_backup_{timestamp}.json"

        backup_data = {
            "timestamp": timestamp,
            "skills": [],
            "stats": self.get_stats(),
        }

        for skill_name, skill_info in self.installed_skills.items():
            if skill_info.local_path and Path(skill_info.local_path).exists():
                try:
                    with open(skill_info.local_path, "r", encoding="utf-8") as f:
                        code_content = f.read()

                    backup_data["skills"].append({
                        "name": skill_name,
                        "code": code_content,
                        "metadata": skill_info.dict(),
                    })
                except Exception as e:
                    print(f"⚠️ 备份技能失败 {skill_name}: {e}")

        try:
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)

            print(f"✅ 技能备份完成: {backup_file}")
            return True

        except Exception as e:
            print(f"❌ 备份失败: {e}")
            return False


# 便捷函数
def create_skill_manager() -> GitHubSkillManager:
    """创建技能管理器实例"""
    return GitHubSkillManager()


# 测试代码
def test_skill_manager():
    """测试技能管理器"""
    print("=" * 60)
    print("测试GitHub技能管理器")
    print("=" * 60)

    try:
        # 创建管理器
        manager = create_skill_manager()

        # 测试1: 列出已安装技能
        print("\n1. 列出已安装技能:")
        installed_skills = manager.list_installed_skills()
        print(f"   找到 {len(installed_skills)} 个本地技能")
        for skill in installed_skills[:3]:
            print(f"   - {skill.name}")

        # 测试2: 路径转换（核心修复验证）
        print("\n2. 测试路径转换（Windows 路径修复）:")
        test_path = "Kylopro-Nexus\\skills\\test_skill.py"
        normalized = _normalize_path(test_path)
        print(f"   原始路径: {test_path}")
        print(f"   转换后:   {normalized}")
        assert "/" in normalized, "路径转换失败！"
        print("   ✅ 路径转换正常")

        # 测试3: 统计信息
        print("\n3. 统计信息:")
        stats = manager.get_stats()
        for key, value in stats.items():
            print(f"   {key}: {value}")

        print("\n" + "=" * 60)
        print("测试完成!")
        print("\n现在你可以:")
        print("  1. 使用有效token连接GitHub仓库")
        print("  2. 搜索和下载云端技能")
        print("  3. 上传自己开发的技能（路径已自动修复）")
        print("  4. 动态加载和运行技能")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 运行测试
    success = test_skill_manager()
    sys.exit(0 if success else 1)
