"""
KyloBrain · ide_bridge_enhanced.py
=====================================
IDE 动手能力层 —— VS Code + Antigravity 平台 深度集成

架构：
  IDEBridge (抽象基类)
    ├── VSCodeBridge     → VS Code REST API / CLI 操作
    ├── AntigravityBridge → 外部平台操作（通用适配器）
    └── IDEOrchestrator  → 统一调度 + 结果写入大脑

动手能力范围：
  · 读写文件、运行代码、捕获输出
  · VS Code：打开文件、运行 terminal 命令、读取 problems 面板
  · Antigravity/其他平台：操作 API、状态同步
  · 所有结果自动写入 brain/warm/episodes (ActionLoop 闭环)

依赖：
  · VS Code REST API（vscode-server 或 code --status）
  · subprocess（标准库）
  · 不依赖 pyautogui / selenium 等重型库
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional
import urllib.request
import urllib.error

BASE_DIR   = Path(os.environ.get("KYLOPRO_DIR", Path.home() / "Kylopro-Nexus"))
BRAIN_DIR  = BASE_DIR / "brain"

# VS Code 相关
VSCODE_EXT_DIR = Path.home() / ".vscode" / "extensions"
VSCODE_SERVER_PORT = int(os.environ.get("VSCODE_SERVER_PORT", "8765"))

# Antigravity 相关（从环境变量读，不硬编码）
ANTIGRAVITY_API_BASE = os.environ.get("ANTIGRAVITY_API_BASE", "")
ANTIGRAVITY_TOKEN    = os.environ.get("ANTIGRAVITY_TOKEN", "")


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


# ══════════════════════════════════════════════
# 执行结果数据类
# ══════════════════════════════════════════════

class ActionResult:
    """统一的执行结果格式，供大脑记录"""

    def __init__(
        self, action: str, success: bool,
        output: str = "", error: str = "",
        duration_sec: float = 0.0,
        metadata: dict = None,
    ) -> None:
        self.action       = action
        self.success      = success
        self.output       = output[:2000]   # 截断，避免撑爆
        self.error        = error[:500]
        self.duration_sec = duration_sec
        self.metadata     = metadata or {}
        self.timestamp    = time.time()

    def to_dict(self) -> dict:
        return {
            "action":       self.action,
            "success":      self.success,
            "output":       self.output,
            "error":        self.error,
            "duration_sec": round(self.duration_sec, 2),
            "metadata":     self.metadata,
            "timestamp":    self.timestamp,
        }

    def __repr__(self) -> str:
        icon = "✅" if self.success else "❌"
        return f"ActionResult({icon} {self.action} | {self.duration_sec:.1f}s)"


# ══════════════════════════════════════════════
# 抽象基类
# ══════════════════════════════════════════════

class IDEBridge(ABC):
    """所有 IDE/平台 桥接的基类"""

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def run_command(self, cmd: str, cwd: Optional[str] = None) -> ActionResult: ...

    @abstractmethod
    def read_file(self, path: str) -> ActionResult: ...

    @abstractmethod
    def write_file(self, path: str, content: str) -> ActionResult: ...

    def _timed(self, fn, *args, **kwargs) -> tuple[Any, float]:
        start = time.time()
        result = fn(*args, **kwargs)
        return result, time.time() - start


# ══════════════════════════════════════════════
# VS Code 桥接
# ══════════════════════════════════════════════

class VSCodeBridge(IDEBridge):
    """
    VS Code 深度集成。

    操作层级（优先级从高到低）：
      1. VS Code REST Server（需要安装 ms-vscode.remote-server 扩展）
      2. code CLI（code --status / code --install-extension）
      3. 直接文件系统操作（读写工作区文件）
      4. subprocess 运行终端命令

    所有操作的输出都被捕获并可写入大脑。
    """

    def __init__(self, workspace: Optional[str] = None) -> None:
        self.workspace    = Path(workspace) if workspace else BASE_DIR
        self._server_url  = f"http://localhost:{VSCODE_SERVER_PORT}"
        self._server_ok: Optional[bool] = None

    # ── 基础能力检测 ──

    def is_available(self) -> bool:
        """检测 VS Code 是否可用（CLI 或 Server）"""
        return self._check_cli() or self._check_server()

    def _check_cli(self) -> bool:
        try:
            r = subprocess.run(
                ["code", "--version"], capture_output=True, timeout=5
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_server(self) -> bool:
        if self._server_ok is not None:
            return self._server_ok
        try:
            req = urllib.request.Request(f"{self._server_url}/api/ping")
            with urllib.request.urlopen(req, timeout=3):
                self._server_ok = True
                return True
        except Exception:
            self._server_ok = False
            return False

    # ── 核心操作 ──

    def run_command(self, cmd: str, cwd: Optional[str] = None) -> ActionResult:
        """
        在 VS Code 集成终端 / 系统终端 运行命令。
        捕获 stdout/stderr，超时保护。
        """
        work_dir = str(cwd or self.workspace)
        start = time.time()
        try:
            # Windows: 使用 PowerShell 或 cmd
            is_win = sys.platform == "win32"
            shell_cmd = ["powershell", "-Command", cmd] if is_win else ["bash", "-c", cmd]
            proc = subprocess.run(
                shell_cmd,
                cwd=work_dir,
                capture_output=True,
                timeout=60,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            success = proc.returncode == 0
            return ActionResult(
                action=f"run:{cmd[:60]}",
                success=success,
                output=proc.stdout,
                error=proc.stderr,
                duration_sec=time.time() - start,
                metadata={"returncode": proc.returncode, "cwd": work_dir},
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                action=f"run:{cmd[:60]}", success=False,
                error="命令超时（60s）", duration_sec=60.0,
            )
        except Exception as e:
            return ActionResult(
                action=f"run:{cmd[:60]}", success=False,
                error=str(e), duration_sec=time.time() - start,
            )

    def read_file(self, path: str) -> ActionResult:
        start = time.time()
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / path
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            return ActionResult(
                action=f"read:{path}", success=True,
                output=content, duration_sec=time.time() - start,
                metadata={"size_bytes": p.stat().st_size},
            )
        except Exception as e:
            return ActionResult(
                action=f"read:{path}", success=False,
                error=str(e), duration_sec=time.time() - start,
            )

    def write_file(self, path: str, content: str) -> ActionResult:
        start = time.time()
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / path
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ActionResult(
                action=f"write:{path}", success=True,
                output=f"写入 {len(content)} 字符",
                duration_sec=time.time() - start,
            )
        except Exception as e:
            return ActionResult(
                action=f"write:{path}", success=False,
                error=str(e), duration_sec=time.time() - start,
            )

    # ── VS Code 专属操作 ──

    def open_file(self, path: str) -> ActionResult:
        """在 VS Code 中打开文件"""
        return self.run_command(f"code {path}")

    def run_python(self, script_path: str,
                   use_venv: bool = True) -> ActionResult:
        """运行 Python 脚本，自动检测虚拟环境"""
        venv = self._find_venv()
        if use_venv and venv:
            if sys.platform == "win32":
                python = str(venv / "Scripts" / "python.exe")
            else:
                python = str(venv / "bin" / "python")
        else:
            python = sys.executable
        return self.run_command(f'"{python}" "{script_path}"')

    def _find_venv(self) -> Optional[Path]:
        """在工作区中查找虚拟环境"""
        for name in ["venv", ".venv", "env", ".env"]:
            p = self.workspace / name
            if p.exists() and (p / "Scripts" / "python.exe").exists():  # Win
                return p
            if p.exists() and (p / "bin" / "python").exists():  # Unix
                return p
        return None

    def get_problems(self) -> ActionResult:
        """
        获取 VS Code problems 面板内容。
        方法：运行 pylint/mypy 等静态分析工具捕获输出
        """
        result = self.run_command(
            f'python -m py_compile {self.workspace}/**/*.py 2>&1 || true'
        )
        return result

    def install_extension(self, ext_id: str) -> ActionResult:
        return self.run_command(f"code --install-extension {ext_id}")

    def get_git_status(self) -> ActionResult:
        """获取工作区 git 状态"""
        return self.run_command("git status --porcelain", cwd=str(self.workspace))

    def git_commit_all(self, message: str) -> ActionResult:
        """提交所有变更（Kylo 完成任务后的自动提交）"""
        cmds = [
            "git add -A",
            f'git commit -m "{message}"',
        ]
        for cmd in cmds:
            r = self.run_command(cmd, cwd=str(self.workspace))
            if not r.success and "nothing to commit" not in r.output.lower():
                return r
        return ActionResult(
            action="git_commit", success=True,
            output=f"已提交: {message}", duration_sec=0,
        )

    def run_tests(self, test_path: str = "tests") -> ActionResult:
        """运行测试套件，捕获结果供大脑记录"""
        return self.run_command(
            f"python -m pytest {test_path} -v --tb=short 2>&1"
        )

    def patch_file(self, path: str, old_text: str, new_text: str) -> ActionResult:
        """精确替换文件中的代码段（比整个重写安全）"""
        read_result = self.read_file(path)
        if not read_result.success:
            return read_result
        content = read_result.output
        if old_text not in content:
            return ActionResult(
                action=f"patch:{path}", success=False,
                error=f"找不到要替换的代码段: {old_text[:40]!r}",
            )
        new_content = content.replace(old_text, new_text, 1)
        return self.write_file(path, new_content)

    def status_summary(self) -> dict:
        """工作区状态摘要"""
        venv = self._find_venv()
        git  = self.get_git_status()
        return {
            "workspace":   str(self.workspace),
            "venv":        str(venv) if venv else None,
            "git_status":  git.output.strip()[:200] if git.success else "not a git repo",
            "vscode_cli":  self._check_cli(),
            "vscode_server": self._check_server(),
        }


# ══════════════════════════════════════════════
# Antigravity 平台桥接
# ══════════════════════════════════════════════

class AntigravityBridge(IDEBridge):
    """
    Antigravity 平台通用适配器。

    设计原则：
    · 不假设平台内部结构，通过 REST API 交互
    · 所有操作结果写入 brain/warm/world_model（更新数字世界认知）
    · 支持：任务提交、状态查询、结果拉取、资源列表

    配置：
      ANTIGRAVITY_API_BASE = "https://your-platform.com/api"
      ANTIGRAVITY_TOKEN    = "Bearer xxxxx"
    """

    def __init__(
        self,
        api_base: str = ANTIGRAVITY_API_BASE,
        token: str = ANTIGRAVITY_TOKEN,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.token    = token
        self._headers = {
            "Authorization": f"Bearer {token}" if token else "",
            "Content-Type": "application/json",
            "User-Agent": "KyloBrain/2.0",
        }

    def is_available(self) -> bool:
        if not self.api_base:
            return False
        try:
            req = urllib.request.Request(
                f"{self.api_base}/health",
                headers=self._headers,
            )
            with urllib.request.urlopen(req, timeout=5):
                return True
        except Exception:
            return False

    def _request(
        self, method: str, endpoint: str,
        data: Optional[dict] = None,
    ) -> tuple[Optional[dict], str]:
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        req = urllib.request.Request(url, method=method, headers=self._headers)
        if data:
            req.data = json.dumps(data).encode()
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode()), ""
        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return None, str(e)

    def run_command(self, cmd: str, cwd: Optional[str] = None) -> ActionResult:
        """在平台上执行命令（通过任务API）"""
        start = time.time()
        data = {"command": cmd, "cwd": cwd or ""}
        result, err = self._request("POST", "/tasks/run", data)
        if result:
            return ActionResult(
                action=f"ag_run:{cmd[:60]}", success=True,
                output=json.dumps(result),
                duration_sec=time.time() - start,
                metadata={"platform": "antigravity"},
            )
        return ActionResult(
            action=f"ag_run:{cmd[:60]}", success=False,
            error=err, duration_sec=time.time() - start,
        )

    def read_file(self, path: str) -> ActionResult:
        """从平台读取文件"""
        start = time.time()
        result, err = self._request("GET", f"/files?path={path}")
        if result:
            return ActionResult(
                action=f"ag_read:{path}", success=True,
                output=result.get("content", ""),
                duration_sec=time.time() - start,
            )
        return ActionResult(
            action=f"ag_read:{path}", success=False,
            error=err, duration_sec=time.time() - start,
        )

    def write_file(self, path: str, content: str) -> ActionResult:
        start = time.time()
        result, err = self._request("PUT", "/files", {"path": path, "content": content})
        return ActionResult(
            action=f"ag_write:{path}",
            success=result is not None,
            output=str(result), error=err,
            duration_sec=time.time() - start,
        )

    def get_task_status(self, task_id: str) -> ActionResult:
        """查询平台任务状态"""
        start = time.time()
        result, err = self._request("GET", f"/tasks/{task_id}")
        return ActionResult(
            action=f"ag_status:{task_id}",
            success=result is not None,
            output=json.dumps(result) if result else "", error=err,
            duration_sec=time.time() - start,
        )

    def list_resources(self) -> ActionResult:
        """列出平台可用资源（工具、模型、数据集）"""
        start = time.time()
        result, err = self._request("GET", "/resources")
        return ActionResult(
            action="ag_list_resources",
            success=result is not None,
            output=json.dumps(result) if result else "", error=err,
            duration_sec=time.time() - start,
        )

    def update_world_model(self, brain_cold) -> None:
        """
        把平台的资源/状态信息写入大脑的 world_model
        让 Kylo 持续更新对"自己活在什么数字环境"的认知
        """
        if not self.is_available():
            return
        resources_result = self.list_resources()
        if resources_result.success:
            try:
                resources = json.loads(resources_result.output)
                brain_cold.update_world_model({
                    "antigravity": {
                        "api_base":       self.api_base,
                        "available":      True,
                        "resources":      resources,
                        "last_checked":   int(time.time()),
                    }
                })
            except Exception:
                pass


# ══════════════════════════════════════════════
# IDE 编排器（ActionLoop 闭环核心）
# ══════════════════════════════════════════════

class IDEOrchestrator:
    """
    统一调度 VSCode 和 Antigravity，实现 ActionLoop 闭环：
    
      任务 → 选择桥接 → 执行 → 捕获结果
           → 写入大脑 episodes → 更新 world_model
           → 根据得分决定是否重试 → 成功后 git commit

    这是让 Kylo 真正"动手"的核心机制。
    """

    def __init__(
        self,
        workspace: Optional[str] = None,
        brain_warm=None,
        brain_cold=None,
    ) -> None:
        self.vscode  = VSCodeBridge(workspace)
        self.antgrav = AntigravityBridge()
        self._warm   = brain_warm   # WarmMemory 实例
        self._cold   = brain_cold   # ColdMemory 实例
        self._log_dir = _ensure(BRAIN_DIR / "action_logs")

    # ── 主执行接口 ──

    def execute(
        self, task: str, actions: list[dict],
        auto_commit: bool = False,
    ) -> dict:
        """
        执行一组动作，返回综合结果。

        actions 格式：
          [
            {"type": "run",        "cmd": "python test.py"},
            {"type": "write",      "path": "output.py", "content": "..."},
            {"type": "read",       "path": "config.json"},
            {"type": "run_python", "path": "main.py"},
            {"type": "run_tests",  "path": "tests/"},
            {"type": "ag_run",     "cmd": "train model"},
          ]
        """
        start    = time.time()
        results  = []
        errors   = []
        success  = True

        for action in actions:
            result = self._dispatch_action(action)
            results.append(result.to_dict())
            if not result.success:
                success = False
                errors.append(result.error)

        duration = time.time() - start

        # 写入大脑
        if self._warm:
            self._warm.record_episode(
                task=task,
                steps=[a.get("type", "?") + ":" + str(list(a.values())[-1])[:30]
                       for a in actions],
                outcome="所有动作完成" if success else f"失败: {errors[0][:80]}",
                duration_sec=duration,
                success=success,
            )

        # 成功后自动 git commit
        if success and auto_commit:
            self.vscode.git_commit_all(f"[KyloBrain] {task[:60]}")

        # 更新 world_model
        if self._cold and self.antgrav.is_available():
            self.antgrav.update_world_model(self._cold)

        # 保存本地日志
        log = {
            "task": task, "actions": actions, "results": results,
            "success": success, "duration_sec": round(duration, 2),
            "timestamp": int(time.time()),
        }
        log_path = self._log_dir / f"action_{int(time.time())}.json"
        log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2))

        return {
            "success":  success,
            "results":  results,
            "errors":   errors,
            "duration": round(duration, 2),
            "log_path": str(log_path),
        }

    def _dispatch_action(self, action: dict) -> ActionResult:
        t = action.get("type", "")
        if t == "run":
            return self.vscode.run_command(action.get("cmd", ""), action.get("cwd"))
        elif t == "write":
            return self.vscode.write_file(action["path"], action.get("content", ""))
        elif t == "read":
            return self.vscode.read_file(action["path"])
        elif t == "run_python":
            return self.vscode.run_python(action["path"])
        elif t == "run_tests":
            return self.vscode.run_tests(action.get("path", "tests"))
        elif t == "patch":
            return self.vscode.patch_file(action["path"], action["old"], action["new"])
        elif t == "git_commit":
            return self.vscode.git_commit_all(action.get("message", "auto commit"))
        elif t == "ag_run":
            return self.antgrav.run_command(action.get("cmd", ""))
        elif t == "ag_status":
            return self.antgrav.get_task_status(action.get("task_id", ""))
        else:
            return ActionResult(
                action=f"unknown:{t}", success=False,
                error=f"未知动作类型: {t}",
            )

    # ── 高阶工作流 ──

    def write_test_fix_loop(
        self, task: str, file_path: str, code: str,
        test_path: str = None, max_retries: int = 3,
    ) -> dict:
        """
        写代码 → 运行测试 → 如果失败分析错误 → 重试
        这是 ActionLoop 闭环的完整体现
        """
        history = []
        for attempt in range(max_retries):
            # 写入代码
            write_r = self.vscode.write_file(file_path, code)
            if not write_r.success:
                return {"success": False, "error": write_r.error, "attempts": attempt + 1}

            # 运行测试
            test_r = self.vscode.run_tests(test_path or "tests")
            history.append({
                "attempt": attempt + 1,
                "test_output": test_r.output[:500],
                "success": test_r.success,
            })

            if test_r.success or "passed" in test_r.output.lower():
                if self._warm:
                    self._warm.record_episode(
                        task=task, steps=["write", "test"],
                        outcome="测试通过", duration_sec=0, success=True,
                    )
                return {"success": True, "attempts": attempt + 1, "history": history}

            # 分析失败原因（给调用者用于下一次修正）
            error_hint = self._extract_error_hint(test_r.output)
            history[-1]["error_hint"] = error_hint

            if attempt < max_retries - 1:
                print(f"[IDEOrchestrator] 第{attempt+1}次失败，错误：{error_hint}")

        if self._warm:
            self._warm.record_failure(task, f"经{max_retries}次重试仍失败")

        return {"success": False, "attempts": max_retries, "history": history}

    def _extract_error_hint(self, test_output: str) -> str:
        """从测试输出中提取关键错误信息"""
        lines = test_output.split("\n")
        error_lines = [l for l in lines if any(
            kw in l.lower() for kw in ["error", "failed", "exception", "assert", "traceback"]
        )]
        return "\n".join(error_lines[:5]) if error_lines else test_output[-300:]

    # ── 工作区状态 ──

    def full_status(self) -> dict:
        return {
            "vscode":      self.vscode.status_summary(),
            "antigravity": {
                "available": self.antgrav.is_available(),
                "api_base":  self.antgrav.api_base or "未配置",
            },
            "workspace":   str(self.vscode.workspace),
        }


# ══════════════════════════════════════════════
# nanobot Skill 入口
# ══════════════════════════════════════════════

class IDESkill:
    """供 nanobot tools.py 调用的统一接口"""

    def __init__(self, warm_memory=None, cold_memory=None) -> None:
        self.orchestrator = IDEOrchestrator(
            brain_warm=warm_memory,
            brain_cold=cold_memory,
        )

    def handle(self, action: str, params: dict = None) -> dict:
        params = params or {}
        if action == "run":
            r = self.orchestrator.vscode.run_command(
                params.get("cmd", ""), params.get("cwd")
            )
            return r.to_dict()
        elif action == "write":
            r = self.orchestrator.vscode.write_file(
                params["path"], params.get("content", "")
            )
            return r.to_dict()
        elif action == "read":
            r = self.orchestrator.vscode.read_file(params["path"])
            return r.to_dict()
        elif action == "execute":
            return self.orchestrator.execute(
                task=params.get("task", ""),
                actions=params.get("actions", []),
                auto_commit=params.get("auto_commit", False),
            )
        elif action == "write_test_fix":
            return self.orchestrator.write_test_fix_loop(
                task=params.get("task", ""),
                file_path=params["file_path"],
                code=params["code"],
                test_path=params.get("test_path"),
                max_retries=params.get("max_retries", 3),
            )
        elif action == "status":
            return self.orchestrator.full_status()
        elif action == "git_status":
            return self.orchestrator.vscode.get_git_status().to_dict()
        elif action == "run_tests":
            return self.orchestrator.vscode.run_tests(
                params.get("path", "tests")
            ).to_dict()
        elif action == "ag_status":
            return self.orchestrator.antgrav.get_task_status(
                params.get("task_id", "")
            ).to_dict()
        else:
            return {"error": f"Unknown action: {action}",
                    "available": ["run","write","read","execute","write_test_fix",
                                  "status","git_status","run_tests","ag_status"]}


# ══════════════════════════════════════════════
# CLI 测试
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("🛠️  IDE Bridge Enhanced — 测试")
    print("=" * 48)

    vs = VSCodeBridge()

    print("\n[1] VS Code 可用性...")
    print(f"    CLI: {vs._check_cli()}")
    print(f"    Server: {vs._check_server()}")

    print("\n[2] 运行简单命令...")
    result = vs.run_command("echo KyloBrain IDE Bridge OK")
    print(f"    {result}")
    print(f"    输出: {result.output.strip()}")

    print("\n[3] 读写文件测试...")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
        f.write("print('hello from KyloBrain')\n")
        tmp_path = f.name
    read_r = vs.read_file(tmp_path)
    print(f"    读取: {read_r.success} | {read_r.output.strip()}")
    write_r = vs.write_file(tmp_path, "# modified by KyloBrain\nprint('updated')\n")
    print(f"    写入: {write_r.success}")
    Path(tmp_path).unlink(missing_ok=True)

    print("\n[4] Antigravity 连接...")
    ag = AntigravityBridge()
    print(f"    可用: {ag.is_available()}")
    if not ANTIGRAVITY_API_BASE:
        print("    ⚠️  ANTIGRAVITY_API_BASE 未配置")

    print("\n[5] 编排器状态...")
    orch = IDEOrchestrator()
    status = orch.full_status()
    print(f"    工作区: {status['workspace']}")
    print(f"    venv: {status['vscode'].get('venv')}")
    print(f"    git: {status['vscode'].get('git_status','?')[:50]}")

    print("\n✅ IDE Bridge 测试完成")
