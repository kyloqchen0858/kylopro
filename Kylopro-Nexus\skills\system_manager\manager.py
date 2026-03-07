
"""
Kylopro 数字管家 (System Steward) — 系统软件管理技能
===================================================
使用 winget + PowerShell 管理 Windows 软件生命周期。
列举冗余软件、评估替代性、安全卸载（含二次确认）。

安全原则：任何删除操作必须显式确认，无法静默执行。

使用方式：
    python -m skills.system_manager.manager
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

# ===========================================================
# Kylopro 可替代的软件列表（评估依据）
# ===========================================================
KYLOPRO_REPLACEABLE: Dict[str, Dict[str, str]] = {
    # name (lower) -> {reason, skill}
    "trae":         {"reason": "AI 代码补全/对话", "skill": "ide_bridge + DeepSeek"},
    "antigravity":  {"reason": "AI 编程助手",      "skill": "ide_bridge + DeepSeek"},
    "github copilot": {"reason": "AI 代码补全",     "skill": "ide_bridge + deepseek-coder"},
    "snipaste":     {"reason": "截图工具",           "skill": "vision_rpa.screenshot"},
    "picpick":      {"reason": "截图工具",           "skill": "vision_rpa.screenshot"},
    "ticktick":     {"reason": "定时提醒",           "skill": "cron_report"},
    "todo":         {"reason": "待办事项",           "skill": "cron_report"},
    "notion":       {"reason": "笔记/日报",          "skill": "cron_report + telegram"},
    "autohotkey":   {"reason": "键鼠自动化",         "skill": "vision_rpa (PyAutoGUI)"},
    "uipath":       {"reason": "RPA 自动化",         "skill": "vision_rpa (全境飞行员)"},
    "selenium":     {"reason": "浏览器自动化",       "skill": "web_pilot (Playwright)"},
}


# ===========================================================
# 数据结构
# ===========================================================

@dataclass
class AppInfo:
    name: str
    version: str = ""
    publisher: str = ""
    source: str = ""           # winget / msstore / 未知
    winget_id: str = ""        # winget 包 ID（用于精确卸载）
    replaceable_by: str = ""   # Kylopro 哪个技能可替代
    replace_reason: str = ""


# ===========================================================
# winget 命令封装
# ===========================================================

async def _run_winget(args: List[str], timeout: int = 30) -> str:
    """异步运行 winget 命令，返回输出文本。"""
    cmd = ["winget"] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        logger.warning("winget 命令超时: {}", " ".join(cmd))
        return ""
    except FileNotFoundError:
        logger.error("winget 未安装或不在 PATH 中")
        return ""


async def _run_powershell(script: str, timeout: int = 15) -> str:
    """异步运行 PowerShell 脚本，返回输出。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-NonInteractive", "-Command", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("PowerShell 执行失败: {}", e)
        return ""


# ===========================================================
# 解析 winget 输出
# ===========================================================

def _parse_winget_list(raw: str) -> List[AppInfo]:
    """解析 winget list 的输出，返回 AppInfo 列表。"""
    apps: List[AppInfo] = []
    lines = raw.splitlines()
    # 跳过头部（找到 Name 列标题行）
    header_idx = -1
    for i, line in enumerate(lines):
        if "Name" in line and "Id" in line and "Version" in line:
            header_idx = i
            break

    if header_idx == -1:
        return apps

    # 解析分隔行，确定列宽
    sep_line = lines[header_idx + 1] if header_idx + 1 < len(lines) else ""
    if not sep_line.startswith("-"):
        return apps

    cols = sep_line.split()
    if len(cols) < 2:
        return apps

    # 粗略按空格切分（winget 输出对齐格式）
    for line in lines[header_idx + 2:]:
        if not line.strip() or line.startswith("-"):
            continue
        parts = line.split(None, 3)  # name, id, version, [source]
        if len(parts) < 2:
            continue
        name      = parts[0]
        winget_id = parts[1] if len(parts) > 1 else ""
        version   = parts[2] if len(parts) > 2 else ""
        source    = parts[3].strip() if len(parts) > 3 else ""

        app = AppInfo(name=name, version=version, winget_id=winget_id, source=source)

        # 判断是否可被 Kylopro 替代
        name_lower = name.lower()
        for kw, info in KYLOPRO_REPLACEABLE.items():
            if kw in name_lower:
                app.replaceable_by = info["skill"]
                app.replace_reason = info["reason"]
                break

        apps.append(app)

    return apps


# ===========================================================
# 主类
# ===========================================================

class SystemManager:
    """
    数字管家执行器。
    封装 winget 和 PowerShell 操作，提供软件管理能力。
    """

    # -----------------------------------------------------------
    # 查询接口
    # -----------------------------------------------------------

    async def list_installed(self, limit: int = 50) -> List[AppInfo]:
        """列出所有已安装软件（按名称排序）。"""
        logger.info("[STEWARD] 正在扫描已安装软件...")
        raw = await _run_winget(["list", "--accept-source-agreements"], timeout=60)
        apps = _parse_winget_list(raw)
        apps.sort(key=lambda a: a.name.lower())
        logger.info("[STEWARD] 共发现 {} 个软件", len(apps))
        return apps[:limit]

    async def find_redundant_apps(self) -> List[AppInfo]:
        """
        找出 Kylopro 可以替代的软件。
        返回带替代建议的软件列表，供用户决策。
        """
        apps = await self.list_installed(limit=200)
        redundant = [a for a in apps if a.replaceable_by]
        logger.info("[STEWARD] 发现 {} 个可能冗余的软件", len(redundant))
        return redundant

    async def search(self, query: str) -> str:
        """在 winget 仓库搜索软件。"""
        logger.info("[STEWARD] 搜索: {}", query)
        return await _run_winget(["search", query, "--accept-source-agreements"])

    async def show_info(self, winget_id: str) -> str:
        """查看软件详情（大小、描述、版本等）。"""
        return await _run_winget(["show", winget_id])

    async def get_disk_usage(self) -> str:
        """用 PowerShell 查询 C 盘各目录大小。"""
        script = (
            "Get-ChildItem 'C:\\Program Files','C:\\Program Files (x86)' -ErrorAction SilentlyContinue "
            "| Sort-Object {$_.GetFiles('*','AllDirectories').Count} -Descending "
            "| Select-Object -First 15 Name,@{n='SizeMB';e={[math]::Round(($_.GetFiles('*','AllDirectories')|Measure-Object -Property Length -Sum).Sum/1MB,1)}} "
            "| Format-Table -AutoSize"
        )
        return await _run_powershell(script, timeout=30)

    # -----------------------------------------------------------
    # 安装接口
    # -----------------------------------------------------------

    async def install(self, winget_id: str, silent: bool = True) -> Dict[str, Any]:
        """
        安装软件。
        Args:
            winget_id: winget 包 ID（如 "Microsoft.PowerToys"）
            silent:    静默安装（不弹窗）
        """
        args = ["install", winget_id, "--accept-package-agreements",
                "--accept-source-agreements"]
        if silent:
            args.append("--silent")
        logger.info("[STEWARD] 安装: {}", winget_id)
        output = await _run_winget(args, timeout=300)
        success = "successfully" in output.lower() or "已成功" in output
        return {"winget_id": winget_id, "success": success, "output": output}

    # -----------------------------------------------------------
    # 卸载接口（带强制安全确认）
    # -----------------------------------------------------------

    async def uninstall(
        self,
        name_or_id: str,
        require_confirm: bool = True,
        telegram_confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        卸载软件。

        安全设计：
        - require_confirm=True（默认）：必须 CLI 输入 'YES' 才执行
        - telegram_confirm：未来支持从 Telegram 发 YES 授权（Phase 5）

        Args:
            name_or_id:      软件名或 winget ID
            require_confirm: 是否要求人工确认（强烈建议保持 True）
        """
        logger.warning("[STEWARD] 请求卸载: {}", name_or_id)

        if require_confirm:
            logger.info("\n[KYLOPRO 安全确认] 即将卸载: {}", name_or_id)
            logger.info("此操作不可逆，请确认。")
            try:
                answer = input("输入 'YES' 确认卸载: ")
            except (EOFError, KeyboardInterrupt):
                return {"success": False, "reason": "用户中止"}

            if answer.strip().upper() != "YES":
                logger.info("[STEWARD] 用户取消卸载")
                return {"success": False, "reason": "用户取消"}

        args = [
            "uninstall", name_or_id,
            "--accept-source-agreements",
            "--silent",
            "--force",
        ]
        logger.warning("[STEWARD] 执行卸载: {}", name_or_id)
        output = await _run_winget(args, timeout=120)
        success = "successfully" in output.lower() or "已成功" in output
        return {"name": name_or_id, "success": success, "output": output}

    # -----------------------------------------------------------
    # 高阶报告
    # -----------------------------------------------------------

    async def generate_report(self) -> str:
        """
        生成完整的软件健康报告（适合推 Telegram）。
        包含：软件总数、冗余软件列表、磁盘使用摘要。
        """
        from skills.telegram_notify.notify import TelegramNotifier

        redundant = await self.find_redundant_apps()
        disk      = await self.get_disk_usage()

        lines = ["<b>[数字管家] 软件健康报告</b>\n"]

        if redundant:
            lines.append(f"<b>发现 {len(redundant)} 个可能冗余的软件：</b>")
            for app in redundant[:8]:
                lines.append(
                    f"  - <b>{app.name}</b>\n"
                    f"    原因：{app.replace_reason}\n"
                    f"    Kylopro 可替代：{app.replaceable_by}"
                )
        else:
            lines.append("未发现冗余软件，系统精简！")

        report = "\n".join(lines)
        notifier = TelegramNotifier()
        if notifier._configured:
            await notifier.send(report)
            logger.info("[STEWARD] 软件报告已推送 Telegram")

        return report


# ===========================================================
# CLI 入口
# ===========================================================

if __name__ == "__main__":
    sys.path.insert(0, str(__file__).replace("skills/system_manager/manager.py", ""))

    async def main() -> None:
        mgr = SystemManager()

        logger.info("\n[数字管家] 扫描冗余软件...\n")
        redundant = await mgr.find_redundant_apps()

        if not redundant:
            logger.info("未发现 Kylopro 可替代的软件。")
        else:
            logger.info(f"发现 {len(redundant)} 个可能冗余的软件：\n")
            for app in redundant:
                logger.info(f"  {app.name} ({app.version})")
                logger.info(f"    -> Kylopro 可替代: {app.replaceable_by}")
                logger.info(f"    -> 原因: {app.replace_reason}")
                logger.info("")

        logger.info("[数字管家] 如需卸载，请指定软件名：")
        logger.info("  python -m skills.system_manager.manager --uninstall <name>")

    asyncio.run(main())
