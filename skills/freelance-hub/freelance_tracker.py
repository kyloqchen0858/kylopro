"""
FreelanceTracker — 自由职业项目管理核心逻辑
=============================================

数据存储：data/freelance_projects.json（单文件，JSON 格式）
发票输出：output/invoices/

所有操作通过 FreelanceTool 暴露给 nanobot AgentLoop。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _normalize_platform(platform: str) -> str:
    p = (platform or "general").strip().lower()
    if p in {"upwork", "freelancer", "fiverr", "direct", "other", "general"}:
        return p
    return "general"


class FreelanceTracker:
    """管理自由职业项目的完整生命周期。"""

    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._data_file = workspace / "data" / "freelance_projects.json"
        self._invoice_dir = workspace / "output" / "invoices"
        self._freelance_out_dir = workspace / "output" / "freelance"
        self._data_file.parent.mkdir(parents=True, exist_ok=True)
        self._invoice_dir.mkdir(parents=True, exist_ok=True)
        self._freelance_out_dir.mkdir(parents=True, exist_ok=True)

    # ── 画像提炼 ──────────────────────────────────────────────

    def _infer_skills(self, projects: list[dict]) -> list[dict]:
        """Infer skill scores from project metadata and time logs."""
        keyword_map = {
            "python": ["python", "fastapi", "flask", "pandas", "pytest"],
            "javascript": ["javascript", "node", "express", "js"],
            "typescript": ["typescript", "ts", "next.js", "nest"],
            "react": ["react", "frontend", "dashboard", "ui"],
            "automation": ["automation", "bot", "workflow", "agent", "rpa"],
            "api_integration": ["api", "oauth", "webhook", "integration"],
            "data_analysis": ["analysis", "report", "dashboard", "etl", "sql"],
            "devops": ["docker", "deploy", "ci", "cd", "linux"],
        }

        scores = {k: 0.0 for k in keyword_map}
        for p in projects:
            text_parts = [
                p.get("title", ""),
                p.get("description", ""),
                " ".join(n.get("text", "") for n in p.get("notes", [])),
                " ".join(t.get("description", "") for t in p.get("time_logs", [])),
            ]
            blob = " ".join(text_parts).lower()
            hours = float(p.get("total_hours", 0) or 0)
            base = 1.0 + min(hours / 10.0, 5.0)

            for skill, kws in keyword_map.items():
                hit = sum(1 for kw in kws if kw in blob)
                if hit:
                    scores[skill] += base * hit

        if not any(v > 0 for v in scores.values()):
            return []

        max_score = max(scores.values()) or 1.0
        ranked = []
        for skill, raw in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
            if raw <= 0:
                continue
            level = int(round((raw / max_score) * 100))
            ranked.append({"skill": skill, "score": level})
        return ranked

    def _top_project_bullets(self, projects: list[dict], limit: int = 6) -> list[str]:
        ranked = sorted(
            projects,
            key=lambda p: ((p.get("agreed_amount") or p.get("bid_amount") or 0), p.get("total_hours", 0)),
            reverse=True,
        )
        bullets: list[str] = []
        for p in ranked:
            if len(bullets) >= limit:
                break
            amt = p.get("agreed_amount") or p.get("bid_amount") or 0
            cur = p.get("currency", "USD")
            hours = p.get("total_hours", 0)
            status = p.get("status", "unknown")
            bullets.append(
                f"- {p.get('title','Untitled')} ({p.get('client','Unknown')}): {status}, {cur} {amt:,.0f}, {hours}h"
            )
        return bullets

    def _summary_metrics(self, projects: list[dict]) -> dict:
        completed = [p for p in projects if p.get("status") == "completed"]
        active = [p for p in projects if p.get("status") == "active"]
        paid_completed = [p for p in completed if p.get("paid")]
        total_hours = sum(float(p.get("total_hours", 0) or 0) for p in projects)
        total_revenue = sum(float((p.get("agreed_amount") or p.get("bid_amount") or 0)) for p in paid_completed)
        return {
            "total_projects": len(projects),
            "active_projects": len(active),
            "completed_projects": len(completed),
            "paid_completed_projects": len(paid_completed),
            "total_hours": round(total_hours, 1),
            "total_revenue": round(total_revenue, 2),
        }

    def _keyword_coverage(self, text: str, keywords: list[str]) -> dict:
        cleaned = [k.strip() for k in keywords if k and k.strip()]
        if not cleaned:
            return {"requested": [], "hit": [], "missing": [], "coverage": 1.0}

        blob = text.lower()
        hit = [k for k in cleaned if k.lower() in blob]
        missing = [k for k in cleaned if k.lower() not in blob]
        coverage = len(hit) / len(cleaned) if cleaned else 1.0
        return {
            "requested": cleaned,
            "hit": hit,
            "missing": missing,
            "coverage": round(coverage, 3),
        }

    def _platform_hint(self, platform: str) -> str:
        hints = {
            "upwork": "突出交付速度、沟通与长期协作能力，强调可量化成果。",
            "freelancer": "突出预算控制与阶段性交付，强调端到端执行。",
            "fiverr": "突出标准化服务包与快速响应，强调可复用工作流。",
            "direct": "突出业务理解与长期维护能力，强调稳定和信任。",
            "other": "突出跨平台适配能力与需求抽象能力。",
            "general": "突出可量化交付与技术广度。",
        }
        return hints.get(platform, hints["general"])

    def refresh_resume(
        self,
        profile_name: str = "Kylo",
        target_role: str = "Freelance Developer",
        platform: str = "general",
        keywords: Optional[list[str]] = None,
    ) -> dict:
        """Generate a resume snapshot from project history."""
        data = self._load()
        projects = data.get("projects", [])
        if not projects:
            return {
                "success": False,
                "error": "暂无项目数据，无法生成简历更新",
            }

        platform = _normalize_platform(platform)
        keywords = keywords or []
        metrics = self._summary_metrics(projects)
        scoped_projects = projects if platform == "general" else [p for p in projects if p.get("platform") == platform]
        source_projects = scoped_projects or projects
        skills = self._infer_skills(source_projects)[:8]
        bullets = self._top_project_bullets(source_projects, limit=8)
        now = _today()

        lines = [
            f"# Resume Snapshot - {profile_name}",
            "",
            f"Date: {now}",
            f"Target Role: {target_role}",
            f"Platform Focus: {platform}",
            "",
            "## Professional Summary",
            (
                f"Freelance builder with {metrics['total_projects']} tracked projects, "
                f"{metrics['completed_projects']} completed deliveries, "
                f"and {metrics['total_hours']} hours of execution across client work."
            ),
            f"Platform Tailoring Hint: {self._platform_hint(platform)}",
            "",
            "## Highlights",
            *bullets,
            "",
            "## Skill Focus",
        ]

        if skills:
            for s in skills:
                lines.append(f"- {s['skill']}: {s['score']}/100")
        else:
            lines.append("- Pending: need more project detail logs to infer skill strengths")

        lines.extend([
            "",
            "## Core Metrics",
            f"- Total Revenue (paid): {metrics['total_revenue']}",
            f"- Active Projects: {metrics['active_projects']}",
            f"- Paid Completed Projects: {metrics['paid_completed_projects']}",
        ])

        if keywords:
            lines.extend(["", "## Keyword Optimization"]) 
            for kw in keywords:
                lines.append(f"- {kw}")

        resume_text = "\n".join(lines)
        out_file = self._freelance_out_dir / f"resume_snapshot_{platform}_{now}.md"
        out_file.write_text(resume_text, encoding="utf-8")
        latest_file = self._freelance_out_dir / f"resume_{platform}_latest.md"
        latest_file.write_text(resume_text, encoding="utf-8")
        (self._freelance_out_dir / "resume_latest.md").write_text(resume_text, encoding="utf-8")

        keyword_eval = self._keyword_coverage(resume_text, keywords)

        return {
            "success": True,
            "path": str(out_file.relative_to(self._workspace)).replace("\\", "/"),
            "latest": str(latest_file.relative_to(self._workspace)).replace("\\", "/"),
            "summary": resume_text,
            "metrics": metrics,
            "skills": skills,
            "platform": platform,
            "keyword_coverage": keyword_eval,
        }

    def refresh_skills_profile(
        self,
        profile_name: str = "Kylo",
        platform: str = "general",
        keywords: Optional[list[str]] = None,
    ) -> dict:
        """Generate a structured skills profile from project history."""
        data = self._load()
        projects = data.get("projects", [])
        if not projects:
            return {
                "success": False,
                "error": "暂无项目数据，无法生成技能更新",
            }

        platform = _normalize_platform(platform)
        keywords = keywords or []
        scoped_projects = projects if platform == "general" else [p for p in projects if p.get("platform") == platform]
        source_projects = scoped_projects or projects

        metrics = self._summary_metrics(source_projects)
        ranked = self._infer_skills(source_projects)
        now = _today()

        payload = {
            "success": True,
            "profile": profile_name,
            "updated_at": _now_iso(),
            "platform": platform,
            "metrics": metrics,
            "skills": ranked,
            "top_projects": self._top_project_bullets(source_projects, limit=6),
        }
        json_file = self._freelance_out_dir / f"skills_profile_{platform}_latest.json"
        json_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (self._freelance_out_dir / "skills_profile_latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        md_lines = [
            f"# Skills Refresh - {profile_name}",
            "",
            f"Date: {now}",
            f"Platform Focus: {platform}",
            "",
            "## Ranked Skills",
        ]
        for s in ranked[:12]:
            md_lines.append(f"- {s['skill']}: {s['score']}/100")
        if keywords:
            md_lines.extend(["", "## Target Keywords", *[f"- {kw}" for kw in keywords]])
        md_lines.extend(["", "## Evidence Projects", *payload["top_projects"]])
        md_text = "\n".join(md_lines)
        md_file = self._freelance_out_dir / f"skills_refresh_{platform}_latest.md"
        md_file.write_text(md_text, encoding="utf-8")
        (self._freelance_out_dir / "skills_refresh_latest.md").write_text(md_text, encoding="utf-8")

        payload["keyword_coverage"] = self._keyword_coverage(md_text, keywords)

        payload.update({
            "markdown_path": str(md_file.relative_to(self._workspace)).replace("\\", "/"),
            "json_path": str(json_file.relative_to(self._workspace)).replace("\\", "/"),
            "markdown": md_text,
        })
        return payload

    # ── 数据读写 ──────────────────────────────────────────────

    def _load(self) -> dict:
        if self._data_file.exists():
            try:
                return json.loads(self._data_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {"projects": []}
        return {"projects": []}

    def _save(self, data: dict) -> None:
        self._data_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _find_project(self, data: dict, project_id: str) -> Optional[dict]:
        for p in data["projects"]:
            if p["id"] == project_id or p["id"].startswith(project_id):
                return p
        # 也支持按标题模糊匹配
        pid_lower = project_id.lower()
        for p in data["projects"]:
            if pid_lower in p["title"].lower():
                return p
        return None

    # ── 核心操作 ──────────────────────────────────────────────

    def add_project(
        self,
        title: str,
        client: str,
        platform: str = "direct",
        bid_amount: float = 0,
        currency: str = "USD",
        hourly_rate: float = 0,
        description: str = "",
    ) -> dict:
        data = self._load()
        project = {
            "id": uuid.uuid4().hex[:8],
            "title": title,
            "client": client,
            "platform": platform,
            "status": "bidding",
            "bid_amount": bid_amount,
            "agreed_amount": 0,
            "currency": currency,
            "hourly_rate": hourly_rate,
            "description": description,
            "notes": [],
            "time_logs": [],
            "total_hours": 0,
            "paid": False,
            "created_at": _now_iso(),
            "started_at": None,
            "completed_at": None,
        }
        data["projects"].append(project)
        self._save(data)
        return project

    def list_projects(self, status: str = "") -> list[dict]:
        data = self._load()
        projects = data["projects"]
        if status:
            projects = [p for p in projects if p["status"] == status]
        return projects

    def update_project(self, project_id: str, **updates) -> str:
        data = self._load()
        project = self._find_project(data, project_id)
        if not project:
            return f"❌ 未找到项目: {project_id}"

        for key in ("status", "agreed_amount", "paid", "hourly_rate", "description"):
            if key in updates and updates[key] is not None:
                project[key] = updates[key]

        if updates.get("status") == "active" and not project["started_at"]:
            project["started_at"] = _now_iso()
        if updates.get("status") == "completed" and not project["completed_at"]:
            project["completed_at"] = _now_iso()

        if updates.get("note"):
            project["notes"].append({
                "date": _today(),
                "text": updates["note"],
            })

        self._save(data)
        return f"✅ 已更新项目 [{project['id']}] {project['title']}"

    def log_time(self, project_id: str, hours: float, description: str = "") -> str:
        data = self._load()
        project = self._find_project(data, project_id)
        if not project:
            return f"❌ 未找到项目: {project_id}"

        project["time_logs"].append({
            "date": _today(),
            "hours": hours,
            "description": description,
        })
        project["total_hours"] = sum(t["hours"] for t in project["time_logs"])

        self._save(data)
        return (
            f"✅ 已记录 {hours}h — {project['title']}\n"
            f"累计工时: {project['total_hours']}h"
        )

    def generate_invoice(self, project_id: str) -> str:
        data = self._load()
        project = self._find_project(data, project_id)
        if not project:
            return f"❌ 未找到项目: {project_id}"

        amount = project["agreed_amount"] or project["bid_amount"]
        cur = project["currency"]

        lines = [
            f"# Invoice",
            f"",
            f"**Date**: {_today()}",
            f"**Invoice #**: INV-{project['id'].upper()}",
            f"",
            f"---",
            f"",
            f"## Client",
            f"**{project['client']}**",
            f"",
            f"## Project",
            f"**{project['title']}**",
            f"",
            f"Platform: {project['platform']}",
            f"",
        ]

        if project["description"]:
            lines.extend([f"Description: {project['description']}", ""])

        # 工时明细
        if project["time_logs"]:
            lines.extend([
                "## Time Log",
                "",
                "| Date | Hours | Description |",
                "|------|-------|-------------|",
            ])
            for entry in project["time_logs"]:
                lines.append(
                    f"| {entry['date']} | {entry['hours']}h | {entry.get('description', '')} |"
                )
            lines.extend([
                "",
                f"**Total Hours**: {project['total_hours']}h",
                "",
            ])

        lines.extend([
            "## Amount",
            "",
            f"**Total: {cur} {amount:,.2f}**",
            "",
            f"Payment Status: {'✅ Paid' if project['paid'] else '⏳ Pending'}",
            "",
            "---",
            "",
            f"*Generated by Kylopro on {_today()}*",
        ])

        invoice_text = "\n".join(lines)

        # 保存到文件
        filename = f"INV-{project['id'].upper()}_{_today()}.md"
        filepath = self._invoice_dir / filename
        filepath.write_text(invoice_text, encoding="utf-8")

        return f"📄 发票已生成: output/invoices/{filename}\n\n{invoice_text}"

    def dashboard(self) -> str:
        data = self._load()
        projects = data["projects"]

        if not projects:
            return "📊 暂无项目数据\n使用 freelance(action='add', ...) 添加第一个项目"

        active = [p for p in projects if p["status"] == "active"]
        completed = [p for p in projects if p["status"] == "completed"]
        bidding = [p for p in projects if p["status"] == "bidding"]

        # 收入统计
        total_earned = sum(
            (p["agreed_amount"] or p["bid_amount"])
            for p in completed if p["paid"]
        )
        total_pending = sum(
            (p["agreed_amount"] or p["bid_amount"])
            for p in completed if not p["paid"]
        )
        active_value = sum(
            (p["agreed_amount"] or p["bid_amount"])
            for p in active
        )
        total_hours = sum(p["total_hours"] for p in projects)

        # 本月统计
        this_month = datetime.now().strftime("%Y-%m")
        month_completed = [
            p for p in completed
            if p.get("completed_at", "").startswith(this_month)
        ]
        month_earned = sum(
            (p["agreed_amount"] or p["bid_amount"])
            for p in month_completed if p["paid"]
        )

        # 平均时薪
        paid_projects = [p for p in completed if p["paid"] and p["total_hours"] > 0]
        if paid_projects:
            avg_hourly = sum(
                (p["agreed_amount"] or p["bid_amount"]) / p["total_hours"]
                for p in paid_projects
            ) / len(paid_projects)
        else:
            avg_hourly = 0

        # 判断主要货币
        currencies = set(p["currency"] for p in projects)
        cur = "USD" if "USD" in currencies else (list(currencies)[0] if currencies else "USD")

        lines = [
            "📊 **Freelance Dashboard**",
            "",
            f"### 本月 ({this_month})",
            f"  已收款: {cur} {month_earned:,.2f}",
            "",
            f"### 总计",
            f"  已收款: {cur} {total_earned:,.2f}",
            f"  待收款: {cur} {total_pending:,.2f}",
            f"  进行中项目价值: {cur} {active_value:,.2f}",
            f"  总工时: {total_hours:.1f}h",
        ]

        if avg_hourly > 0:
            lines.append(f"  平均时薪: {cur} {avg_hourly:,.2f}/h")

        lines.extend([
            "",
            f"### 项目统计",
            f"  🟡 投标中: {len(bidding)}",
            f"  🟢 进行中: {len(active)}",
            f"  ✅ 已完成: {len(completed)}",
            f"  总项目数: {len(projects)}",
        ])

        # 活跃项目列表
        if active:
            lines.extend(["", "### 当前活跃项目"])
            for p in active:
                amt = p["agreed_amount"] or p["bid_amount"]
                lines.append(
                    f"  · [{p['id']}] {p['title']} — {p['client']} "
                    f"({cur} {amt:,.0f}, {p['total_hours']}h)"
                )

        if bidding:
            lines.extend(["", "### 投标中"])
            for p in bidding:
                lines.append(
                    f"  · [{p['id']}] {p['title']} — {p['client']} "
                    f"(bid: {p['currency']} {p['bid_amount']:,.0f})"
                )

        return "\n".join(lines)
