"""
Kylopro 代码神经元 (Code Neuron) — IDE 桥接技能
================================================
让 Kylopro 拥有完整的 IDE 能力，三层接入方式：
  层1: 文件系统直读（读写代码文件）
  层2: MCP 协议对接（Antigravity/Trae/Claude Dev 等暴露 MCP Server 时）
  层3: Vision RPA 接管（截图 + OCR 操控 IDE 界面）

不依赖任何特定 IDE，可单独运行。

使用方式：
    from skills.ide_bridge.bridge import IDEBridge
    bridge = IDEBridge("c:/MyProject")
    code = await bridge.read_file("src/main.py")
    result = await bridge.run_command("python -m pytest")
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass


# ===========================================================
# 工具函数
# ===========================================================

# 代码文件扩展名白名单
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".c", ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".kt",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml",
    ".md", ".txt", ".sh", ".bat", ".ps1", ".sql", ".xml",
}

# 忽略目录
IGNORE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".idea", ".vscode", "dist", "build", ".cache", "target",
}


def _is_code_file(path: Path) -> bool:
    return path.suffix.lower() in CODE_EXTENSIONS


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORE_DIRS for part in path.parts)


# ===========================================================
# 层1: 文件系统直读
# ===========================================================

class FileSystemLayer:
    """直接读写项目文件，零依赖。"""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        if not self.workspace.exists():
            raise FileNotFoundError(f"工作区不存在: {self.workspace}")

    def get_file_tree(self, max_depth: int = 4, max_files: int = 100) -> dict[str, Any]:
        """
        返回项目文件树（字典格式，省 Token 版本）。
        不发完整路径，只发相对路径和类型。
        """
        tree: dict[str, Any] = {}
        count = 0

        for path in sorted(self.workspace.rglob("*")):
            if count >= max_files:
                break
            if _is_ignored(path.relative_to(self.workspace)):
                continue
            # 限制深度
            rel = path.relative_to(self.workspace)
            if len(rel.parts) > max_depth:
                continue

            if path.is_file() and _is_code_file(path):
                tree[str(rel)] = {"type": "file", "size": path.stat().st_size}
                count += 1
            elif path.is_dir():
                tree[str(rel)] = {"type": "dir"}

        return tree

    def get_file_tree_compact(self, max_depth: int = 4) -> str:
        """以紧凑字符串格式返回文件树（适合发给 LLM）。"""
        lines = [f"[WorkSpace: {self.workspace}]"]
        for path in sorted(self.workspace.rglob("*")):
            if _is_ignored(path.relative_to(self.workspace)):
                continue
            rel = path.relative_to(self.workspace)
            if len(rel.parts) > max_depth:
                continue
            indent = "  " * (len(rel.parts) - 1)
            icon = "📁" if path.is_dir() else "📄"
            lines.append(f"{indent}{icon} {rel.name}")
        return "\n".join(lines[:80])  # 最多80行

    def read_file(self, relative_path: str, max_chars: int = 5000) -> str:
        """读取文件内容（有大小限制）。"""
        path = self.workspace / relative_path
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {relative_path}")
        if not _is_code_file(path):
            raise ValueError(f"不支持的文件类型: {path.suffix}")

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            # 如果UTF-8解码失败，尝试其他常见编码
            try:
                content = path.read_text(encoding="gbk", errors="replace")
                logger.warning("[IDE] 文件 {} 使用GBK编码读取", relative_path)
            except:
                content = path.read_text(encoding="latin-1", errors="replace")
                logger.warning("[IDE] 文件 {} 使用latin-1编码读取", relative_path)
        
        if len(content) > max_chars:
            logger.warning("[IDE] 文件内容已截断 ({} -> {} 字符)", len(content), max_chars)
            content = content[:max_chars] + f"\n... [截断，共 {len(content)} 字符]"
        return content

    def write_file(self, relative_path: str, content: str) -> None:
        """写入文件（自动创建目录）。"""
        path = self.workspace / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            path.write_text(content, encoding="utf-8")
        except UnicodeEncodeError:
            # 如果包含无法用UTF-8编码的字符，使用errors="replace"替换
            path.write_text(content, encoding="utf-8", errors="replace")
            logger.warning("[IDE] 文件 {} 包含无法编码的字符，已替换", relative_path)
        
        logger.info("[IDE] 写入文件: {}", relative_path)

    def find_in_code(self, query: str, extensions: list[str] | None = None) -> list[dict]:
        """在代码库中搜索文本（类 grep 功能）。"""
        results = []
        exts = set(extensions or list(CODE_EXTENSIONS))

        for path in self.workspace.rglob("*"):
            if not path.is_file() or path.suffix not in exts:
                continue
            if _is_ignored(path.relative_to(self.workspace)):
                continue
            try:
                # 使用UTF-8读取，失败时尝试其他编码
                try:
                    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                except UnicodeDecodeError:
                    try:
                        lines = path.read_text(encoding="gbk", errors="replace").splitlines()
                    except:
                        lines = path.read_text(encoding="latin-1", errors="replace").splitlines()
                
                for i, line in enumerate(lines, 1):
                    if query.lower() in line.lower():
                        rel_path = str(path.relative_to(self.workspace))
                        results.append({
                            "file": rel_path,
                            "line": i,
                            "content": line.strip(),
                        })
            except Exception as e:
                logger.warning("[IDE] 读取文件失败 {}: {}", path, e)
                continue

        return results[:50]  # 最多返回50条结果


# ===========================================================
# 层2: MCP 协议对接
# ===========================================================

class MCPLayer:
    """通过 MCP (Model Context Protocol) 与 IDE 通信。"""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.connected = False
        logger.info("[IDE] MCP 层初始化 (工作区: {})", self.workspace)

    async def connect(self) -> bool:
        """尝试连接 MCP Server。"""
        # 这里可以扩展为连接实际的 MCP Server
        await asyncio.sleep(0.1)
        self.connected = True
        logger.info("[IDE] MCP 层已连接")
        return True

    async def read_file(self, relative_path: str) -> str:
        """通过 MCP 读取文件。"""
        if not self.connected:
            raise ConnectionError("MCP 未连接")
        # 模拟 MCP 调用
        path = self.workspace / relative_path
        return await asyncio.to_thread(self._read_file_fallback, path)

    def _read_file_fallback(self, path: Path) -> str:
        """回退到文件系统读取。"""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="gbk", errors="replace")
            except:
                return path.read_text(encoding="latin-1", errors="replace")


# ===========================================================
# 层3: Vision RPA 接管
# ===========================================================

class VisionRPALayer:
    """通过截图 + OCR 操控 IDE 界面（备用方案）。"""

    def __init__(self) -> None:
        self.ready = False
        logger.info("[IDE] Vision RPA 层初始化")

    async def setup(self) -> bool:
        """初始化视觉组件。"""
        # 这里可以初始化 OCR、截图等工具
        await asyncio.sleep(0.1)
        self.ready = True
        logger.info("[IDE] Vision RPA 层就绪")
        return True


# ===========================================================
# 主桥接类
# ===========================================================

class IDEBridge:
    """IDE 桥接主类，整合三层能力。"""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).resolve()
        self.fs = FileSystemLayer(self.workspace)
        self.mcp = MCPLayer(self.workspace)
        self.vision = VisionRPALayer()
        logger.info("[IDE] 桥接器初始化: {}", self.workspace)

    async def read_file(self, relative_path: str, max_chars: int = 5000) -> str:
        """读取文件（优先使用 MCP，失败则回退到文件系统）。"""
        # 尝试 MCP 层
        if self.mcp.connected:
            try:
                content = await self.mcp.read_file(relative_path)
                if len(content) > max_chars:
                    content = content[:max_chars] + f"\n... [截断，共 {len(content)} 字符]"
                return content
            except Exception as e:
                logger.warning("[IDE] MCP 读取失败，回退到文件系统: {}", e)

        # 回退到文件系统
        return self.fs.read_file(relative_path, max_chars)

    async def write_file(self, relative_path: str, content: str) -> None:
        """写入文件（目前仅使用文件系统层）。"""
        self.fs.write_file(relative_path, content)

    async def get_file_tree(self, compact: bool = True) -> str | dict:
        """获取文件树。"""
        if compact:
            return self.fs.get_file_tree_compact()
        return self.fs.get_file_tree()

    async def run_command(self, command: str, cwd: str | None = None) -> dict:
        """在项目目录中运行 shell 命令。"""
        work_dir = Path(cwd) if cwd else self.workspace
        work_dir = work_dir.resolve()

        logger.info("[IDE] 执行命令: {} (cwd: {})", command, work_dir)

        try:
            # 使用 UTF-8 编码处理命令输出
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            stdout_bytes, stderr_bytes = await process.communicate()

            # 解码输出，使用 errors="replace" 处理编码问题
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            return {
                "success": process.returncode == 0,
                "returncode": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        except Exception as e:
            logger.error("[IDE] 命令执行失败: {}", e)
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": str(e),
            }

    async def search_in_code(self, query: str, extensions: list[str] | None = None) -> list[dict]:
        """在代码中搜索文本。"""
        return self.fs.find_in_code(query, extensions)

    async def connect_mcp(self) -> bool:
        """连接 MCP 层。"""
        return await self.mcp.connect()

    async def setup_vision(self) -> bool:
        """初始化视觉层。"""
        return await self.vision.setup()


# ===========================================================
# 快捷函数
# ===========================================================

async def quick_read(workspace: str, file_path: str) -> str:
    """快速读取文件。"""
    bridge = IDEBridge(workspace)
    return await bridge.read_file(file_path)


async def quick_write(workspace: str, file_path: str, content: str) -> None:
    """快速写入文件。"""
    bridge = IDEBridge(workspace)
    await bridge.write_file(file_path, content)


async def quick_tree(workspace: str) -> str:
    """快速获取文件树。"""
    bridge = IDEBridge(workspace)
    return await bridge.get_file_tree()


# ===========================================================
# 测试
# ===========================================================

async def _test() -> None:
    """简单测试。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        bridge = IDEBridge(tmpdir)

        # 测试写入和读取
        test_content = "print('你好，世界！')  # 包含中文\nprint('Hello, World!')"
        await bridge.write_file("test.py", test_content)

        read_back = await bridge.read_file("test.py")
        print("读取内容:", read_back)
        assert test_content in read_back

        # 测试文件树
        tree = await bridge.get_file_tree()
        print("文件树:", tree[:200] if isinstance(tree, str) else "...")


if __name__ == "__main__":
    asyncio.run(_test())