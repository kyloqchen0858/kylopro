"""
Kylopro 自主实验员 (Autonomous Experimenter)
===========================================
允许 Kylopro 在不破坏核心代码的前提下，
在 data/experiments/ 目录下进行代码原型验证、Bug 修复实验或新功能预演。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from loguru import logger
from core.config import PROJECT_ROOT, DATA_DIR

class AutonomousExperiment:
    """
    自主实验引擎。
    """

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace) if workspace else PROJECT_ROOT
        self.exp_dir = DATA_DIR / "experiments"
        self.exp_dir.mkdir(parents=True, exist_ok=True)

    async def run_experiment(
        self,
        code: str,
        name: str = "test",
        timeout: int = 30
    ) -> dict[str, Any]:
        """
        运行一段实验代码并返回结果。
        """
        exp_id = uuid.uuid4().hex[:6]
        filename = f"exp_{name}_{exp_id}.py"
        file_path = self.exp_dir / filename
        
        # 1. 写入实验文件
        try:
            file_path.write_text(code, encoding="utf-8")
            logger.info(f"[Experiment] 实验文件已创建: {filename}")
        except Exception as e:
            return {"success": False, "error": f"写入实验文件失败: {e}"}

        # 2. 运行实验 (使用当前环境的 Python)
        try:
            # 在子进程中运行
            process = await asyncio.create_subprocess_exec(
                "python", str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workspace
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                return_code = process.returncode
                
                return {
                    "success": return_code == 0,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "returncode": return_code,
                    "file_path": str(file_path)
                }
            except asyncio.TimeoutExpired:
                process.kill()
                return {"success": False, "error": f"实验运行超时 ({timeout}s)"}
                
        except Exception as e:
            return {"success": False, "error": f"执行实验时发生异常: {e}"}

    def cleanup(self, filename: str):
        """清理实验文件。"""
        file_path = self.exp_dir / filename
        if file_path.exists():
            file_path.unlink()
            logger.info(f"[Experiment] 已清理实验文件: {filename}")
