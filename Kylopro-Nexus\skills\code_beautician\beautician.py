"""
Kylopro 代码美容师 (Code Beautician)
======================================
Kylopro 的自我审视与进化模块：
  1. 本地 AST 扫描 skills/ — 零 Token 发现代码问题
  2. 依赖版本检测 — 找出可升级的 pip 包
  3. deepseek-coder 精准优化 — 只发 AST 摘要，省 Token
  4. 自动重写（需用户确认）— 改完立刻触发 verifier 自检

API 配置（.env）：
  CODE_REVIEW_API_KEY  — 正式密钥上线后填入；留空自动回退至 DEEPSEEK_API_KEY
  CODE_REVIEW_MODEL    — 默认 deepseek-coder
  CODE_REVIEW_BASE_URL — 默认 https://api.deepseek.com
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
except AttributeError:
    pass

SKILLS_ROOT = Path(__file__).parent.parent

# ===========================================================
# deepseek-coder 客户端（优先用专属 key，回退至通用 key）
# ===========================================================

def _get_review_client():
    """获取代码审查专用的 LLM 客户端。"""
    from openai import AsyncOpenAI

    api_key  = os.getenv("CODE_REVIEW_API_KEY", "") or os.getenv("DEEPSEEK_API_KEY", "")
    model    = os.getenv("CODE_REVIEW_MODEL",    "deepseek-coder")
    base_url = os.getenv("CODE_REVIEW_BASE_URL", "https://api.deepseek.com")

    if not api_key or api_key.startswith("your_"):
        return None, model
    return AsyncOpenAI(api_key=api_key, base_url=base_url), model


# ===========================================================
# 代码问题数据结构
# ===========================================================

@dataclass
class CodeIssue:
    file:        str
    line:        int  = 0
    severity:    str  = "info"   # info | warn | error
    category:    str  = ""       # complexity | missing-type | bare-except | etc
    message:     str  = ""


@dataclass
class SkillAuditResult:
    skill_name:  str
    file_count:  int  = 0
    line_count:  int  = 0
    issues:      list[CodeIssue] = field(default_factory=list)
    ai_review:   str  = ""       # deepseek-coder 的建议（若已调用）
    needs_update: list[str] = field(default_factory=list)  # 可升级的依赖

    @property
    def score(self) -> int:
        """健康分 0-100（问题越少分越高）。"""
        deduct = sum(
            {"error": 10, "warn": 5, "info": 1}.get(i.severity, 0)
            for i in self.issues
        )
        return max(0, 100 - deduct)


# ===========================================================
# 本地 AST 扫描（零 Token）
# ===========================================================

def _ast_scan_file(path: Path) -> list[CodeIssue]:
    """
    用 AST 扫描单个 Python 文件，返回代码问题列表。
    纯本地，零 Token 消耗。
    """
    issues = []
    fname = str(path)

    try:
        code = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(code)
    except SyntaxError as e:
        return [CodeIssue(file=fname, line=e.lineno or 0, severity="error",
                          category="syntax", message=str(e))]
    except Exception:
        return []

    lines = code.splitlines()

    for node in ast.walk(tree):

        # 1. 函数过长（超过 60 行告警）
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end   = getattr(node, "end_lineno", node.lineno)
            length = end - node.lineno
            if length > 60:
                issues.append(CodeIssue(
                    file=fname, line=node.lineno, severity="warn",
                    category="complexity",
                    message=f"函数 `{node.name}` 过长 ({length} 行)，建议拆分",
                ))

            # 2. 缺少类型注解（函数参数未注解）
            args_without_annotation = [
                a.arg for a in node.args.args
                if a.arg != "self" and a.annotation is None
            ]
            if args_without_annotation and node.name not in ("__init__", "main"):
                issues.append(CodeIssue(
                    file=fname, line=node.lineno, severity="info",
                    category="missing-type",
                    message=f"函数 `{node.name}` 的参数缺少类型注解: {args_without_annotation}",
                ))

        # 3. 裸 except（捕获所有异常，难以调试）
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(CodeIssue(
                file=fname, line=node.lineno, severity="warn",
                category="bare-except",
                message="裸 except: 捕获了所有异常，建议指定具体异常类型",
            ))

        # 4. print 语句残留（生产代码应用 logger）
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                issues.append(CodeIssue(
                    file=fname, line=node.lineno, severity="info",
                    category="print-stmt",
                    message="发现 print()，生产代码建议替换为 logger.info()",
                ))

        # 5. TODO/FIXME 注释未处理
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            s = str(node.value.value)
            if any(kw in s.upper() for kw in ("TODO", "FIXME", "HACK", "XXX")):
                issues.append(CodeIssue(
                    file=fname, line=node.lineno, severity="info",
                    category="todo-marker",
                    message=f"未处理的标记: {s[:60]}",
                ))

    # 6. 检查行内 TODO 注释
    for i, line in enumerate(lines, 1):
        if any(kw in line.upper() for kw in ("# TODO", "# FIXME", "# HACK")):
            issues.append(CodeIssue(
                file=fname, line=i, severity="info",
                category="todo-comment",
                message=line.strip()[:80],
            ))

    return issues


def _scan_skill_dir(skill_dir: Path) -> SkillAuditResult:
    """扫描单个 skill 目录，返回审计结果。"""
    result = SkillAuditResult(skill_name=skill_dir.name)
    py_files = list(skill_dir.glob("*.py"))
    result.file_count = len(py_files)

    for f in py_files:
        try:
            result.line_count += len(f.read_text(encoding="utf-8", errors="replace").splitlines())
        except Exception:
            pass
        result.issues.extend(_ast_scan_file(f))

    return result


# ===========================================================
# 依赖版本检测（本地 pip，零 Token）
# ===========================================================

def _check_outdated_deps() -> list[dict[str, str]]:
    """检查可升级的 pip 包（pip list --outdated）。"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except Exception as e:
        logger.warning("[BEAUTICIAN] 依赖检测失败: {}", e)
        return []


# ===========================================================
# deepseek-coder 精准审查（只发摘要，省 Token）
# ===========================================================

async def _ai_review(skill_name: str, issues: list[CodeIssue], code_snippet: str) -> str:
    """
    把本地 AST 发现的问题 + 代码片段发给 deepseek-coder，获取优化建议。
    省 Token 原则：只发 AST 摘要 + 最相关代码片段（不超过 80 行）。
    """
    client, model = _get_review_client()
    if not client:
        return "（CODE_REVIEW_API_KEY 未配置，跳过 AI 审查。填入密钥后可启用）"

    # 构建精简 prompt（Token 经济）
    issue_summary = "\n".join(
        f"  [{i.severity.upper()}] L{i.line} [{i.category}] {i.message}"
        for i in issues[:10]
    ) or "  （未发现结构性问题）"

    prompt = f"""技能名: {skill_name}
本地静态分析发现的问题:
{issue_summary}

代码片段（前80行）:
```python
{code_snippet[:2000]}
```

请给出3-5条最高优先级的具体优化建议。
要求: 简洁、可执行、符合 Python 最佳实践。
不要重复已列出的问题，重点给出解决方案。"""

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("[BEAUTICIAN] AI 审查失败: {}", e)
        return f"（AI 审查失败: {e}）"


# ===========================================================
# 主类
# ===========================================================

class CodeBeautician:
    """
    代码美容师：扫描 skills/、发现问题、AI 优化建议、可选自动重写。
    """

    def __init__(self, skills_root: Path | None = None) -> None:
        self.skills_root = skills_root or SKILLS_ROOT

    # -----------------------------------------------------------
    # 扫描
    # -----------------------------------------------------------

    async def audit_skill(
        self,
        skill_name: str,
        with_ai: bool = True,
    ) -> SkillAuditResult:
        """审计单个技能。"""
        skill_dir = self.skills_root / skill_name
        if not skill_dir.exists():
            raise FileNotFoundError(f"技能不存在: {skill_name}")

        result = _scan_skill_dir(skill_dir)
        logger.info("[BEAUTICIAN] 扫描 {} — {} 个问题，健康分 {}",
                    skill_name, len(result.issues), result.score)

        # 如果有问题，用 deepseek-coder 提供优化建议
        if with_ai and (result.issues or True):
            # 读取主文件源码
            main_py = skill_dir / f"{skill_name.split('_')[-1]}.py"
            if not main_py.exists():
                py_files = list(skill_dir.glob("*.py"))
                main_py  = py_files[0] if py_files else None

            snippet = ""
            if main_py and main_py.exists():
                snippet = main_py.read_text(encoding="utf-8", errors="replace")

            result.ai_review = await _ai_review(skill_name, result.issues, snippet)

        return result

    async def run_full_audit(
        self,
        with_ai: bool = True,
        notify_telegram: bool = True,
    ) -> dict[str, SkillAuditResult]:
        """
        全量审计所有 skills/ 目录，生成综合报告。
        """
        logger.info("[BEAUTICIAN] 开始全量代码审计...")

        # 发现所有 skill 目录（排除 skill_evolution 自身避免递归）
        skill_dirs = [
            d for d in self.skills_root.iterdir()
            if d.is_dir() and not d.name.startswith("_")
            and d.name != "code_beautician"
        ]

        # 并发扫描（AST 是 CPU 密集，但文件小，并发没问题）
        tasks   = {d.name: self.audit_skill(d.name, with_ai=with_ai) for d in skill_dirs}
        results: dict[str, SkillAuditResult] = {}
        for name, coro in tasks.items():
            try:
                results[name] = await coro
            except Exception as e:
                logger.warning("[BEAUTICIAN] 扫描 {} 失败: {}", name, e)

        # 检查依赖
        outdated = _check_outdated_deps()
        logger.info("[BEAUTICIAN] 完成审计: {} 个技能，{} 个可更新依赖",
                    len(results), len(outdated))

        if notify_telegram:
            await self._push_audit_report(results, outdated)

        return results

    # -----------------------------------------------------------
    # 报告
    # -----------------------------------------------------------

    async def _push_audit_report(
        self,
        results: dict[str, SkillAuditResult],
        outdated_deps: list[dict],
    ) -> None:
        """推送美容报告到 Telegram。"""
        try:
            from skills.telegram_notify.notify import TelegramNotifier
            notifier = TelegramNotifier()
            if not notifier._configured:
                return

            lines = ["<b>[美容师] 代码健康报告</b>\n"]

            # 技能健康评分
            lines.append("<b>技能健康评分：</b>")
            for name, r in sorted(results.items(), key=lambda x: x[1].score):
                bar    = "█" * (r.score // 10) + "░" * (10 - r.score // 10)
                issues = len(r.issues)
                lines.append(
                    f"  {name}: [{bar}] {r.score}/100 ({issues} 问题)"
                )

            # 总结问题
            total_issues = sum(len(r.issues) for r in results.values())
            lines.append(f"\n共 {len(results)} 个技能，{total_issues} 个代码问题")

            # 依赖更新
            if outdated_deps[:5]:
                lines.append("\n<b>可更新依赖：</b>")
                for pkg in outdated_deps[:5]:
                    lines.append(
                        f"  - {pkg['name']}: {pkg['version']} → {pkg['latest_version']}"
                    )

            # 最差技能 AI 建议
            worst = min(results.values(), key=lambda r: r.score, default=None)
            if worst and worst.ai_review:
                lines.append(f"\n<b>优先优化 [{worst.skill_name}]：</b>")
                lines.append(worst.ai_review[:400])

            await notifier.send("\n".join(lines))
        except Exception as e:
            logger.warning("[BEAUTICIAN] Telegram 推送失败: {}", e)

    # -----------------------------------------------------------
    # 自动修复（需确认）
    # -----------------------------------------------------------

    async def auto_fix(
        self,
        skill_name: str,
        require_confirm: bool = True,
    ) -> dict[str, Any]:
        """
        用 deepseek-coder 重写指定技能的主文件。
        Human-in-the-Loop: 必须确认才执行。
        """
        client, model = _get_review_client()
        if not client:
            return {"success": False, "reason": "CODE_REVIEW_API_KEY 未配置"}

        skill_dir = self.skills_root / skill_name
        py_files  = list(skill_dir.glob("*.py"))
        if not py_files:
            return {"success": False, "reason": "无 Python 文件"}

        # 选主文件
        main_py = next((f for f in py_files if f.name not in ("__init__.py",)), py_files[0])
        original = main_py.read_text(encoding="utf-8", errors="replace")

        # 先审计
        audit = await self.audit_skill(skill_name, with_ai=False)
        issue_text = "\n".join(
            f"L{i.line} [{i.category}] {i.message}" for i in audit.issues[:10]
        )

        # deepseek-coder 重写
        prompt = f"""以下是 Kylopro 项目中 {skill_name} 技能的代码，请按照如下问题进行优化重写：

已发现的问题：
{issue_text or '无明显问题'}

要求：
1. 保持原有功能 100% 不变
2. 修复以上问题
3. 添加缺失的类型注解
4. 确保有完整中文注释（关键业务逻辑处）
5. 不引入新的外部依赖

原始代码（完整）:
```python
{original}
```

只返回重写后的完整 Python 代码，不要任何解释。"""

        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.05,
            )
            new_code = resp.choices[0].message.content or ""
            # 提取代码块内容
            if "```python" in new_code:
                new_code = new_code.split("```python")[1].split("```")[0]
        except Exception as e:
            return {"success": False, "reason": f"AI 重写失败: {e}"}

        if require_confirm:
            print(f"\n[美容师] 即将重写 {main_py.name}")
            print(f"  原始: {len(original)} 字符 → 新版: {len(new_code)} 字符")
            print(f"  发现 {len(audit.issues)} 个问题")
            try:
                ans = input("输入 'YES' 确认覆盖: ")
            except (EOFError, KeyboardInterrupt):
                return {"success": False, "reason": "用户中止"}
            if ans.strip().upper() != "YES":
                return {"success": False, "reason": "用户取消"}

        # 备份原文件
        backup = main_py.with_suffix(f".bak.{datetime.now().strftime('%Y%m%d%H%M%S')}")
        backup.write_text(original, encoding="utf-8")
        logger.info("[BEAUTICIAN] 已备份原文件: {}", backup.name)

        # 写入新代码
        main_py.write_text(new_code, encoding="utf-8")
        logger.info("[BEAUTICIAN] {} 已重写", main_py.name)

        # 触发 verifier 自检
        from skills.skill_evolution.verifier import SkillVerifier
        check = await SkillVerifier().run_one(skill_name)
        logger.info("[BEAUTICIAN] 自检结果: {}", check["status"])

        return {
            "success":     True,
            "file":        str(main_py),
            "backup":      str(backup),
            "issues_fixed": len(audit.issues),
            "verify":      check["status"],
        }


# ===========================================================
# CLI 入口
# ===========================================================

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    async def main() -> None:
        b = CodeBeautician()
        print("[美容师] 开始全量审计...\n")
        results = await b.run_full_audit(with_ai=True, notify_telegram=True)
        for name, r in sorted(results.items(), key=lambda x: x[1].score):
            print(f"  {name}: {r.score}/100 ({len(r.issues)} 问题, {r.line_count} 行)")
        print("\n报告已推送 Telegram。")

    asyncio.run(main())
