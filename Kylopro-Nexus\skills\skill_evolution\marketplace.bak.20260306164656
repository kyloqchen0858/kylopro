"""
Kylopro 技能市场 (Skill Marketplace)
=====================================
自主进化引擎：搜索 -> 安全扫描 -> 用户确认 -> 部署 -> 自检

流程：
  1. 搜索  — GitHub API + PyPI 联网查找相关技能/库
  2. 评估  — DeepSeek-chat 生成技能说明书 (省 Token：只评估摘要)
  3. 安全  — AST 静态扫描 + 危险模式检测（本地，零 Token）
  4. 确认  — Telegram 推送报告，等待用户 YES（Human-in-the-Loop）
  5. 部署  — 写入 skills/，动态加载，运行自检验证
  6. 报告  — 推送技能说明书到 Telegram

安全原则（.coredeveloprule §4）：
  - 只写 skills/，绝不改 core/
  - 部署前必须人工确认
  - API Key 零硬编码
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import importlib.util
import json
import re
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

SKILLS_ROOT = Path(__file__).parent.parent


# ===========================================================
# 危险代码模式（AST + 正则，本地扫描，零 Token）
# ===========================================================

# 危险导入（绝对禁止）
FORBIDDEN_IMPORTS = {
    "os.system", "subprocess.call", "subprocess.Popen",
    "ctypes", "socket", "ftplib", "smtplib",
    "mmap", "winreg", "shutil.rmtree",
}

# 危险函数调用模式（用 AST 检测）
FORBIDDEN_CALLS = {
    "eval", "exec", "compile", "__import__", "open",  # open 须审查
    "system", "popen", "call", "Popen",
}

# 正则危险模式
DANGER_PATTERNS = [
    r"os\.system\s*\(",
    r"subprocess\.(call|Popen|run)\s*\(",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__\s*\(",
    r"socket\.(connect|bind)\s*\(",
    r"requests\.(get|post)\s*\(",   # 未经批准的网络请求
    r"urllib\.request\.urlopen",
    r"base64\.b64decode",           # 常见混淆手法
    r"chr\(\d+\)",                  # chr 拼接混淆
]


def _security_scan(code: str) -> dict[str, Any]:
    """
    对代码进行安全扫描（纯本地 AST + 正则，零网络请求，零 Token）。

    返回：
    {
        "safe": bool,
        "risk_level": "safe" | "low" | "medium" | "high",
        "findings": [...],
        "summary": str,
    }
    """
    findings = []

    # 1. 语法检查（能解析就通过）
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {
            "safe": False,
            "risk_level": "high",
            "findings": [f"语法错误: {e}"],
            "summary": "代码无法解析，拒绝部署",
        }

    # 2. AST 遍历检查
    for node in ast.walk(tree):
        # 检查导入
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
            else:
                module = node.module or ""
            for forbidden in FORBIDDEN_IMPORTS:
                if module.startswith(forbidden.split(".")[0]):
                    findings.append(f"[WARN] 检测到导入: {module}")

        # 检查函数调用
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            if func_name in FORBIDDEN_CALLS and func_name != "open":
                findings.append(f"[WARN] 危险函数调用: {func_name}()")

    # 3. 正则检查（捕获 AST 可能遗漏的动态构造）
    for pattern in DANGER_PATTERNS:
        if re.search(pattern, code):
            findings.append(f"[WARN] 危险模式: {pattern}")

    # 4. 硬编码 key 检查（最常见安全问题）
    key_patterns = [
        r'["\']sk-[a-zA-Z0-9]{20,}["\']',    # OpenAI/DeepSeek key
        r'["\']AIzaSy[a-zA-Z0-9_-]{33}["\']', # Google API key
        r'(?i)password\s*=\s*["\'][^"\']+["\']',
        r'(?i)secret\s*=\s*["\'][^"\']+["\']',
    ]
    for kp in key_patterns:
        if re.search(kp, code):
            findings.append("[HIGH] 检测到可能硬编码的密钥！")

    # 综合评估
    high_count   = sum(1 for f in findings if "[HIGH]" in f)
    warn_count   = sum(1 for f in findings if "[WARN]" in f)

    if high_count > 0:
        risk_level = "high"
        safe       = False
    elif warn_count >= 3:
        risk_level = "medium"
        safe       = False
    elif warn_count > 0:
        risk_level = "low"
        safe       = True   # 低风险：警告用户但允许部署
    else:
        risk_level = "safe"
        safe       = True

    return {
        "safe":       safe,
        "risk_level": risk_level,
        "findings":   findings,
        "summary":    f"风险等级: {risk_level.upper()}，发现 {len(findings)} 个问题" if findings
                      else "安全扫描通过",
    }


# ===========================================================
# GitHub 搜索
# ===========================================================

async def _search_github(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """
    通过 GitHub Search API 搜索相关仓库。
    返回精简结果（省 Token：只传名称/描述/链接，不传 README）。
    """
    url = "https://api.github.com/search/repositories"
    params = {
        "q":        f"{query} language:python",
        "sort":     "stars",
        "order":    "desc",
        "per_page": max_results,
    }
    headers = {
        "Accept":     "application/vnd.github+json",
        "User-Agent": "Kylopro-SkillMarketplace/1.0",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data  = resp.json()
            items = data.get("items", [])
            return [
                {
                    "name":        item["full_name"],
                    "description": item.get("description", "")[:200],
                    "stars":       item["stargazers_count"],
                    "url":         item["html_url"],
                    "clone_url":   item["clone_url"],
                    "topics":      item.get("topics", [])[:5],
                }
                for item in items
            ]
    except Exception as e:
        logger.warning("[MARKETPLACE] GitHub 搜索失败: {}", e)
        return []


async def _search_pypi(query: str, max_results: int = 3) -> list[dict[str, Any]]:
    """搜索 PyPI 包（补充 GitHub 搜索）。"""
    url = f"https://pypi.org/search/?q={query}&format=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp  = await client.get(f"https://pypi.org/search/?q={query}")
            # PyPI 不提供 JSON API，用简单正则提取包名
            names = re.findall(r'class="package-snippet__name"[^>]*>([^<]+)<', resp.text)[:max_results]
            return [{"name": n.strip(), "url": f"https://pypi.org/project/{n.strip()}/"}
                    for n in names if n.strip()]
    except Exception as e:
        logger.warning("[MARKETPLACE] PyPI 搜索失败: {}", e)
        return []


# ===========================================================
# 搜索结果 + DeepSeek 评估
# ===========================================================

async def _evaluate_with_deepseek(
    query: str,
    github_results: list[dict],
    pypi_results: list[dict],
) -> str:
    """
    用 DeepSeek-chat 评估搜索结果，生成技能推荐报告。
    Token 经济: 只发摘要数据，不发 README 全文。
    """
    import os
    from openai import AsyncOpenAI

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return "（DeepSeek 未配置，跳过智能评估）"

    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # 构建紧凑的数据摘要（省 Token）
    gh_summary = "\n".join(
        f"- [{r['name']}]({r['url']}) ⭐{r['stars']}: {r['description'][:80]}"
        for r in github_results[:3]
    )
    pypi_summary = "\n".join(
        f"- [{r['name']}]({r['url']})" for r in pypi_results[:2]
    )

    prompt = f"""用户需求: {query}

GitHub 搜索结果:
{gh_summary or '无结果'}

PyPI 包:
{pypi_summary or '无结果'}

请用3-5句话:
1. 推荐最适合 Kylopro 的选项（要求: Python 库、轻量、少依赖）
2. 说明如何以最小 Token 代价集成到 skills/ 目录
3. 如果都不适合，建议直接用现有技能组合实现

回复要简洁，像技术总监给助手下指令。"""

    try:
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("[MARKETPLACE] DeepSeek 评估失败: {}", e)
        return f"（评估失败: {e}）"


# ===========================================================
# 主类
# ===========================================================

class SearchResult:
    """封装一个搜索结果，包含安全扫描状态。"""

    def __init__(self, data: dict[str, Any]) -> None:
        self.raw      = data
        self.name     = data.get("name", "unknown")
        self.url      = data.get("url", "")
        self.desc     = data.get("description", "")
        self.stars    = data.get("stars", 0)
        self.scan     : dict[str, Any] | None = None  # 安全扫描结果（延迟）

    def __repr__(self) -> str:
        return f"<SearchResult {self.name} ⭐{self.stars}>"


class SkillMarketplace:
    """
    技能市场：搜索 → 评估 → 安全扫描 → 用户确认 → 部署 → 自检。
    """

    def __init__(self) -> None:
        self.skills_root = SKILLS_ROOT
        self._notifier = None

    def _get_notifier(self):
        if not self._notifier:
            from skills.telegram_notify.notify import TelegramNotifier
            self._notifier = TelegramNotifier()
        return self._notifier

    # -----------------------------------------------------------
    # 1. 搜索
    # -----------------------------------------------------------

    async def search(self, query: str, push_telegram: bool = True) -> list[SearchResult]:
        """
        联网搜索 GitHub + PyPI，用 DeepSeek 生成推荐报告，
        推送到 Telegram 等待用户决策。

        Args:
            query:         用户需求（自然语言）
            push_telegram: 是否推送搜索报告到 Telegram
        """
        logger.info("[MARKETPLACE] 搜索: {}", query)

        # 并发搜索
        gh_results, pypi_results = await asyncio.gather(
            _search_github(query),
            _search_pypi(query),
        )

        # DeepSeek 评估
        eval_text = await _evaluate_with_deepseek(query, gh_results, pypi_results)

        # 构建搜索结果对象
        results = [SearchResult(r) for r in gh_results]

        # 推 Telegram
        if push_telegram:
            await self._push_search_report(query, results, pypi_results, eval_text)

        return results

    async def _push_search_report(
        self,
        query: str,
        gh: list[SearchResult],
        pypi: list[dict],
        eval_text: str,
    ) -> None:
        """推送搜索结果到 Telegram。"""
        notifier = self._get_notifier()
        if not notifier._configured:
            return

        lines = [f"<b>[MARKETPLACE] 技能搜索报告</b>\n需求：{query}\n"]

        if gh:
            lines.append("<b>GitHub 候选：</b>")
            for r in gh[:3]:
                lines.append(f'  <a href="{r.url}">{r.name}</a> ⭐{r.stars}')
                if r.desc:
                    lines.append(f"  {r.desc[:80]}")
        if pypi:
            lines.append("\n<b>PyPI 包：</b>")
            for p in pypi[:2]:
                lines.append(f'  <a href="{p["url"]}">{p["name"]}</a>')

        lines.append(f"\n<b>AI 推荐：</b>\n{eval_text}")
        lines.append("\n回复 <code>deploy [项目名]</code> 以安全部署，或 <code>skip</code> 跳过。")

        await notifier.send("\n".join(lines))

    # -----------------------------------------------------------
    # 2. 安全扫描
    # -----------------------------------------------------------

    async def scan_url(self, raw_url: str) -> dict[str, Any]:
        """
        下载指定 URL 的 Python 文件并进行安全扫描。
        只扫描，不执行，不写磁盘。
        """
        logger.info("[MARKETPLACE] 安全扫描: {}", raw_url)
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(raw_url)
                resp.raise_for_status()
                code = resp.text
        except Exception as e:
            return {"safe": False, "risk_level": "error", "findings": [str(e)], "summary": f"下载失败: {e}"}

        scan = _security_scan(code)
        scan["url"]  = raw_url
        scan["size"] = len(code)
        logger.info("[MARKETPLACE] 扫描结果: {}", scan["summary"])
        return scan

    def scan_code(self, code: str) -> dict[str, Any]:
        """对代码字符串直接进行安全扫描。"""
        return _security_scan(code)

    # -----------------------------------------------------------
    # 3. 部署
    # -----------------------------------------------------------

    async def deploy_code(
        self,
        skill_name: str,
        code: str,
        skill_md: str = "",
        require_confirm: bool = True,
    ) -> dict[str, Any]:
        """
        将代码安全部署到 skills/ 目录。

        流程：
          1. AST 安全扫描
          2. 用户确认（若 require_confirm=True）
          3. 写入 skills/<skill_name>/
          4. 运行 SkillVerifier 自检
          5. 推送技能说明书到 Telegram
        """
        # 1. 安全扫描
        scan = _security_scan(code)
        logger.info("[MARKETPLACE] 部署 {} — 安全评估: {}", skill_name, scan["summary"])

        if scan["risk_level"] == "high":
            msg = f"[BLOCKED] 安全扫描拒绝部署 '{skill_name}'\n风险: {scan['findings']}"
            logger.error(msg)
            return {"success": False, "reason": "安全扫描拒绝", "scan": scan}

        # 2. 人工确认（.coredeveloprule §4 硬性要求）
        if require_confirm:
            confirm_msg = (
                f"\n[MARKETPLACE] 即将部署技能: {skill_name}\n"
                f"安全评级: {scan['risk_level'].upper()}\n"
                f"发现 {len(scan['findings'])} 个提示\n"
                f"输入 'YES' 确认部署: "
            )
            try:
                answer = input(confirm_msg)
            except (EOFError, KeyboardInterrupt):
                return {"success": False, "reason": "用户中止"}
            if answer.strip().upper() != "YES":
                return {"success": False, "reason": "用户取消"}

        # 3. 写入 skills/
        skill_dir = self.skills_root / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "__init__.py").write_text(f'"""Auto-deployed skill: {skill_name}"""', encoding="utf-8")
        (skill_dir / "skill.py").write_text(code, encoding="utf-8")
        if skill_md:
            (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

        logger.info("[MARKETPLACE] 已写入: skills/{}/", skill_name)

        # 4. 动态导入验证
        try:
            spec   = importlib.util.spec_from_file_location(
                f"skills.{skill_name}.skill",
                str(skill_dir / "skill.py"),
            )
            mod    = importlib.util.module_from_spec(spec)  # type: ignore
            spec.loader.exec_module(mod)  # type: ignore
            import_ok = True
        except Exception as e:
            logger.error("[MARKETPLACE] 动态导入失败: {}", e)
            import_ok = False

        # 5. 推送技能说明书
        await self._push_deploy_report(skill_name, scan, import_ok, skill_md)

        return {
            "success":   import_ok,
            "skill_dir": str(skill_dir),
            "scan":      scan,
        }

    async def _push_deploy_report(
        self,
        skill_name: str,
        scan: dict,
        import_ok: bool,
        skill_md: str,
    ) -> None:
        """部署完成后推 Telegram 技能说明书。"""
        notifier = self._get_notifier()
        if not notifier._configured:
            return

        status = "[OK] 部署成功" if import_ok else "[FAIL] 导入失败"
        msg = (
            f"<b>[MARKETPLACE] 新技能部署报告</b>\n\n"
            f"技能名称: <code>{skill_name}</code>\n"
            f"安全评级: {scan['risk_level'].upper()}\n"
            f"部署状态: {status}\n"
        )
        if skill_md:
            # 截取 SKILL.md 前 3 行作为摘要
            preview = "\n".join(skill_md.splitlines()[:6])
            msg += f"\n<b>技能说明书预览：</b>\n<code>{preview}</code>"

        await notifier.send(msg)

    # -----------------------------------------------------------
    # 快捷方法：搜索 + 提示用户下一步
    # -----------------------------------------------------------

    async def suggest(self, user_need: str) -> str:
        """
        根据用户自然语言需求，快速推荐实现路径。
        优先用现有技能组合，真的缺才搜索。
        """
        EXISTING_SKILLS = {
            "截图": "vision_rpa.screenshot_to_telegram",
            "监控文件": "file_monitor",
            "定时": "cron_report",
            "安装软件": "system_manager.install",
            "卸载软件": "system_manager.uninstall",
            "网页": "web_pilot",
            "浏览器": "web_pilot",
            "点击": "vision_rpa.find_and_click",
            "代码": "ide_bridge",
            "git": "ide_bridge.run_command",
            "telegram": "telegram_notify",
        }

        # 先查现有技能
        existing = [v for k, v in EXISTING_SKILLS.items() if k in user_need]
        if existing:
            return f"现有技能可以实现：{', '.join(existing)}\n无需搜索新技能，Token 零消耗。"

        # 确实需要新技能，去搜索
        results = await self.search(user_need, push_telegram=True)
        return f"已搜索并推送 {len(results)} 个候选到 Telegram，请确认后回复 deploy。"


# ===========================================================
# CLI 入口
# ===========================================================

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    async def main() -> None:
        import sys
        query = " ".join(sys.argv[1:]) or "定时截图并发送 Telegram"
        market = SkillMarketplace()
        results = await market.search(query)
        print(f"\n找到 {len(results)} 个候选:")
        for r in results:
            print(f"  {r.name} ⭐{r.stars}: {r.desc[:60]}")
            print(f"  -> {r.url}")

    asyncio.run(main())
