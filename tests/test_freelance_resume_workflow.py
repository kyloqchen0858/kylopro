from __future__ import annotations

import json
from pathlib import Path

from skills.kylobrain.cloud_brain import ensure_dirs  # smoke import shared env


def _seed_projects(path: Path) -> None:
    payload = {
        "projects": [
            {
                "id": "p001",
                "title": "AI Automation Dashboard",
                "client": "Acme",
                "platform": "upwork",
                "status": "completed",
                "bid_amount": 1200,
                "agreed_amount": 1500,
                "currency": "USD",
                "hourly_rate": 60,
                "description": "Python FastAPI + React dashboard with API integration",
                "notes": [{"date": "2026-03-01", "text": "Delivered webhook integration"}],
                "time_logs": [
                    {"date": "2026-02-25", "hours": 8, "description": "build backend api"},
                    {"date": "2026-02-27", "hours": 6, "description": "react frontend"},
                ],
                "total_hours": 14,
                "paid": True,
                "created_at": "2026-02-20T10:00:00",
                "started_at": "2026-02-22T09:00:00",
                "completed_at": "2026-03-01T18:00:00",
            },
            {
                "id": "p002",
                "title": "Workflow Bot Maintenance",
                "client": "Beta",
                "platform": "direct",
                "status": "active",
                "bid_amount": 600,
                "agreed_amount": 800,
                "currency": "USD",
                "hourly_rate": 50,
                "description": "Agent workflow automation and testing",
                "notes": [{"date": "2026-03-05", "text": "Improved retry strategy"}],
                "time_logs": [{"date": "2026-03-06", "hours": 5, "description": "automation tuning"}],
                "total_hours": 5,
                "paid": False,
                "created_at": "2026-03-03T10:00:00",
                "started_at": "2026-03-04T09:00:00",
                "completed_at": None,
            },
        ]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_freelance_resume_and_skills_refresh(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("KYLOPRO_DIR", str(tmp_path))
    ensure_dirs()

    workspace = Path(tmp_path)
    data_file = workspace / "data" / "freelance_projects.json"
    _seed_projects(data_file)

    import importlib.util

    tracker_path = workspace / "skills" / "freelance-hub" / "freelance_tracker.py"
    # Use source file from repo; tests run in workspace where this path may not exist.
    if not tracker_path.exists():
        tracker_path = Path(__file__).resolve().parents[1] / "skills" / "freelance-hub" / "freelance_tracker.py"

    spec = importlib.util.spec_from_file_location("freelance_tracker", tracker_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    tracker = mod.FreelanceTracker(workspace)

    resume = tracker.refresh_resume(
        profile_name="Kylo",
        target_role="Freelance AI Engineer",
        platform="upwork",
        keywords=["python", "react", "api integration"],
    )
    assert resume["success"] is True
    assert "resume_upwork_latest.md" in resume["latest"]
    assert (workspace / resume["latest"]).exists()
    assert "keyword_coverage" in resume
    assert 0 <= resume["keyword_coverage"]["coverage"] <= 1

    skills = tracker.refresh_skills_profile(
        profile_name="Kylo",
        platform="upwork",
        keywords=["automation", "dashboard"],
    )
    assert skills["success"] is True
    assert len(skills["skills"]) > 0
    assert skills["platform"] == "upwork"
    assert (workspace / skills["json_path"]).exists()
    assert (workspace / skills["markdown_path"]).exists()
