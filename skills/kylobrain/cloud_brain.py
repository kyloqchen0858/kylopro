"""
KyloBrain · cloud_brain.py
===========================
三层记忆系统 + 觉醒协议 + 云端同步

架构：
  HOT   → MEMORY.md          (~2KB, 直接进LLM context)
  WARM  → brain/warm/*.jsonl  (本地结构化, 语义检索)
  COLD  → GitHub Gist (私有)  (无限云端归档)

觉醒三角冗余：
  HOT丢失  → 从WARM episodes重建摘要
  WARM丢失 → 从COLD下载patterns+achievements重建
  COLD断连 → HOT+WARM维持运行，恢复后推送
  全丢失   → 从 SOUL.md + DEVLOG.md 重建身份

零额外依赖：只用Python标准库 + json文件
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional
import urllib.error
import urllib.request


# ══════════════════════════════════════════════
# 全局配置
# ══════════════════════════════════════════════

def _resolve_base_dir() -> Path:
    env_dir = os.environ.get("KYLOPRO_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    # skills/kylobrain/cloud_brain.py -> Kylopro-Nexus/
    repo_guess = Path(__file__).resolve().parents[2]
    cwd = Path.cwd().resolve()
    home_guess = Path.home() / "Kylopro-Nexus"
    for candidate in (repo_guess, cwd, home_guess):
        if (candidate / "brain").exists() and (candidate / "skills").exists():
            return candidate
    return repo_guess


BASE_DIR = _resolve_base_dir()
BRAIN_DIR       = BASE_DIR / "brain"
MEMORY_FILE     = BASE_DIR / "MEMORY.md"
SOUL_FILE       = BASE_DIR / "SOUL.md"
DEVLOG_FILE     = BASE_DIR / "DEVLOG.md"
DECISIONS_DIR   = BASE_DIR / "decisions"
LEARNING_DIR    = BASE_DIR / "learning"

def _load_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token
    try:
        try:
            from skills.kylobrain.credential_vault import get_vault
        except ImportError:
            from credential_vault import get_vault
        return get_vault().get("github_kylo") or ""
    except Exception:
        return ""


GITHUB_TOKEN    = _load_github_token()
GIST_ID_ENV     = os.environ.get("KYLOBRAIN_GIST_ID", "")

HOT_MAX_BYTES           = 2000    # MEMORY.md 上限
WARM_RECENT_DAYS        = 14      # "温"的定义
COLD_SYNC_INTERVAL_H    = 24      # 冷层同步间隔
COLD_CACHE_VALID_H      = 24      # 本地缓存有效期


# ══════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════

def ensure_dirs() -> None:
    for d in [BRAIN_DIR, DECISIONS_DIR, LEARNING_DIR,
              BRAIN_DIR / "warm", BRAIN_DIR / "cold_cache",
              BRAIN_DIR / "snapshots"]:
        d.mkdir(parents=True, exist_ok=True)


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_week() -> str:
    return datetime.now().strftime("%Y_W%V")


def short_id(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:8]


def file_hash(path: Path) -> str:
    """计算文件内容哈希，用于变更检测"""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def tokenize(text: str) -> set[str]:
    """零依赖中英文分词"""
    words = re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]", text.lower())
    return set(words)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    i = len(a & b)
    u = len(a | b)
    return i / u if u else 0.0


def _get_vector_backend():
    try:
        from skills.kylobrain.vector_backend import get_vector_backend
        return get_vector_backend()
    except ImportError:
        try:
            from vector_backend import get_vector_backend
            return get_vector_backend()
        except ImportError:
            return None


def github_request(
    method: str, url: str,
    token: str, data: Optional[dict] = None,
    timeout: int = 12
) -> Optional[dict]:
    """最小化GitHub API调用，不依赖requests"""
    req = urllib.request.Request(
        url, method=method,
        headers={
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "User-Agent": "KyloBrain/2.0",
            "Accept": "application/vnd.github.v3+json",
        }
    )
    if data:
        req.data = json.dumps(data).encode()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[ColdMemory] GitHub {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"[ColdMemory] Network: {e}")
        return None


# ══════════════════════════════════════════════
# 第一层：HOT 记忆（MEMORY.md）
# ══════════════════════════════════════════════

class HotMemory:
    """
    管理 MEMORY.md。
    · 大小超限时自动把最老条目降级到 WARM
    · 每次写入前做快照哈希（觉醒三角所需）
    · summarize_to_hot：记忆巩固 —— 多条细节 → 一条精华
    """

    def __init__(self) -> None:
        ensure_dirs()
        self.path = MEMORY_FILE
        self._snap_dir = BRAIN_DIR / "snapshots"

    # ── 读写 ──

    def read(self) -> str:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return ""

    def write(self, content: str) -> None:
        self._snapshot_before_write()
        self.path.write_text(content, encoding="utf-8")

    def _snapshot_before_write(self) -> None:
        """写入前保存快照，用于觉醒恢复"""
        if not self.path.exists():
            return
        snap = self._snap_dir / f"hot_{now_ts()}.md"
        snap.write_bytes(self.path.read_bytes())
        # 只保留最近5个快照，避免磁盘堆积
        snaps = sorted(self._snap_dir.glob("hot_*.md"))
        for old in snaps[:-5]:
            old.unlink(missing_ok=True)

    # ── 添加条目 ──

    def add_entry(self, content: str, category: str = "general") -> dict:
        current = self.read()
        entry = f"\n[{now_ts()}][{category}] {content}"
        new_content = current + entry
        if len(new_content.encode()) > HOT_MAX_BYTES:
            new_content = self._demote_oldest(current) + entry
        self.write(new_content)
        return {
            "status": "added",
            "size_bytes": len(new_content.encode()),
            "limit_bytes": HOT_MAX_BYTES,
        }

    def _demote_oldest(self, content: str) -> str:
        lines = [l for l in content.split("\n") if l.strip()]
        if not lines:
            return content
        WarmMemory().store_demoted(lines[0])
        return "\n".join(lines[1:])

    # ── 记忆巩固 ──

    def summarize_to_hot(self, summary: str) -> None:
        """把多条旧记忆替换为一条精华摘要"""
        lines = [l for l in self.read().split("\n") if l.strip()]
        if len(lines) > 5:
            old = "\n".join(lines[:-3])
            recent = "\n".join(lines[-3:])
            WarmMemory().store_consolidated(old, summary)
            self.write(f"[CONSOLIDATED][{now_ts()}] {summary}\n{recent}")

    # ── 状态 ──

    def size_kb(self) -> float:
        return len(self.read().encode()) / 1024

    def hash(self) -> str:
        return file_hash(self.path)

    def get_latest_snapshot(self) -> Optional[Path]:
        snaps = sorted(self._snap_dir.glob("hot_*.md"))
        return snaps[-1] if snaps else None


# ══════════════════════════════════════════════
# 第二层：WARM 记忆（本地 JSONL）
# ══════════════════════════════════════════════

class WarmMemory:
    """
    本地 JSONL 存储。五个 collection：
      episodes   – 任务执行历史（情节记忆）
      patterns   – 技能模式（直觉来源）
      failures   – 失败记录（规避风险）
      demoted    – 从HOT降级的条目
      consolidated – HOT巩固时保留的原始内容
    检索：Jaccard相似度，零依赖，无向量数据库
    """

    def __init__(self) -> None:
        ensure_dirs()
        self.dir = BRAIN_DIR / "warm"
        self.vector = _get_vector_backend()

    # ── 基础IO ──

    def _file(self, name: str) -> Path:
        return self.dir / f"{name}.jsonl"

    def vector_status(self) -> dict:
        backend_status = self.vector.status() if self.vector else {
            "available": False,
            "operational": False,
            "store_dir": str(BRAIN_DIR / "vector_store"),
            "error": "vector backend unavailable",
            "last_runtime_error": None,
        }
        return {
            **backend_status,
            "retrieval_mode": "vector" if backend_status.get("operational") else "jaccard",
            "fallback_reason": backend_status.get("last_runtime_error") or backend_status.get("error"),
        }

    def append(self, collection: str, record: dict) -> None:
        record.setdefault("_ts", time.time())
        record.setdefault("_id", short_id(str(record)))
        with open(self._file(collection), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            if self.vector and self.vector.available():
                self.vector.upsert_record(collection, record)
        except Exception:
            pass

    def read_all(self, collection: str) -> list[dict]:
        p = self._file(collection)
        if not p.exists():
            return []
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows

    def read_recent(self, collection: str, days: int = WARM_RECENT_DAYS) -> list[dict]:
        cutoff = time.time() - days * 86400
        return [r for r in self.read_all(collection) if r.get("_ts", 0) > cutoff]

    def rewrite(self, collection: str, records: list[dict]) -> None:
        with open(self._file(collection), "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        try:
            if self.vector and self.vector.available():
                self.vector.replace_collection(collection, records)
        except Exception:
            pass

    # ── 情节记忆 ──

    def record_episode(
        self, task: str, steps: list[str],
        outcome: str, duration_sec: float,
        success: bool, score: int = 0,
        tags: list[str] = None,
    ) -> None:
        self.append("episodes", {
            "task": task,
            "steps": steps,
            "outcome": outcome,
            "duration_sec": duration_sec,
            "success": success,
            "score": score,
            "tags": tags or [],
            "task_tokens": list(tokenize(task)),
        })

    # ── 技能模式（直觉） ──

    def upsert_pattern(
        self, task_type: str, method: str,
        new_success: bool, sample_weight: float = 0.3,
    ) -> None:
        """指数移动平均更新成功率"""
        patterns = self.read_all("patterns")
        for p in patterns:
            if p.get("task_type") == task_type and p.get("method") == method:
                old_rate = p.get("success_rate", 0.5)
                p["success_rate"] = (1 - sample_weight) * old_rate + sample_weight * float(new_success)
                p["sample_count"] = p.get("sample_count", 0) + 1
                p["_updated"] = time.time()
                self.rewrite("patterns", patterns)
                return
        self.append("patterns", {
            "task_type": task_type,
            "method": method,
            "success_rate": float(new_success),
            "sample_count": 1,
        })

    # ── 失败记录 ──

    def record_failure(self, task: str, error: str, recovery: str = "") -> None:
        self.append("failures", {
            "task": task,
            "error": error,
            "recovery": recovery,
            "task_tokens": list(tokenize(task)),
            "error_tokens": list(tokenize(error)),
        })

    # ── 降级接收 ──

    def store_demoted(self, entry: str) -> None:
        self.append("demoted", {"content": entry, "demoted_at": now_ts()})

    def store_consolidated(self, original: str, summary: str) -> None:
        self.append("consolidated", {
            "original": original[:600],
            "summary": summary,
        })

    # ── 语义检索（Jaccard） ──

    def search(
        self, query: str, collection: str,
        top_k: int = 5, threshold: float = 0.12,
        days: Optional[int] = None,
    ) -> list[dict]:
        if self.vector and self.vector.available():
            try:
                hits = self.vector.search(collection, query, top_k=top_k, days=days)
                if hits:
                    rows = self.read_recent(collection, days) if days else self.read_all(collection)
                    by_id = {row.get("_id"): row for row in rows}
                    found = []
                    for hit in hits:
                        row = by_id.get(hit.get("_id"))
                        if row:
                            enriched = dict(row)
                            enriched["_score"] = hit.get("_score", 0.0)
                            found.append(enriched)
                    if found:
                        return found
            except Exception:
                pass

        q_tok = tokenize(query)
        rows = self.read_recent(collection, days) if days else self.read_all(collection)
        scored = []
        for r in rows:
            r_tok = set(r.get("task_tokens") or r.get("error_tokens") or [])
            if not r_tok:
                r_tok = tokenize(" ".join(str(v) for v in r.values() if isinstance(v, str)))
            sim = jaccard(q_tok, r_tok)
            if sim >= threshold:
                scored.append((sim, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def find_similar_failure(self, task: str) -> Optional[dict]:
        results = self.search(task, "failures", top_k=1, threshold=0.18, days=90)
        return results[0] if results else None

    def find_best_pattern(self, task: str) -> Optional[dict]:
        patterns = self.read_all("patterns")
        if not patterns:
            return None
        q_tok = tokenize(task)
        best_score, best = 0.0, None
        for p in patterns:
            sim = jaccard(q_tok, tokenize(p.get("task_type", "")))
            score = sim * 0.6 + p.get("success_rate", 0) * 0.4
            if score > best_score:
                best_score, best = score, p
        return best if best_score > 0.08 else None

    # ── 统计 ──

    def stats(self) -> dict:
        vector = self.vector_status()
        return {
            "episodes":          len(self.read_all("episodes")),
            "patterns":          len(self.read_all("patterns")),
            "failures":          len(self.read_all("failures")),
            "episodes_recent14": len(self.read_recent("episodes")),
            "vector_enabled":    bool(vector.get("available")),
            "vector_operational": bool(vector.get("operational")),
            "retrieval_mode":    vector.get("retrieval_mode"),
            "vector":            vector,
        }

    def rebuild_from_cold(self, cold_data: dict) -> None:
        """觉醒三角：从COLD数据重建WARM层"""
        if "patterns" in cold_data:
            self.rewrite("patterns", cold_data["patterns"])
        if "achievements" in cold_data:
            # achievements 转成情节记忆
            for ach in cold_data.get("achievements", []):
                self.record_episode(
                    task=ach.get("title", ""),
                    steps=["achievement"],
                    outcome=ach.get("description", ""),
                    duration_sec=0,
                    success=True,
                    tags=["achievement", ach.get("impact", "medium")],
                )
        print(f"[WarmMemory] 从COLD重建完成: {self.stats()}")


# ══════════════════════════════════════════════
# 第三层：COLD 记忆（GitHub Gist 私有）
# ══════════════════════════════════════════════

class ColdMemory:
    """
    GitHub Gist（私有）作为无限云端归档。
    
    Gist 文件结构：
      brain_manifest.json  – 索引 + 健康状态
      patterns.json        – 最有价值的技能模式
      achievements.json    – 成就记录
      world_model.json     – 对数字世界的理解
      weekly_YYYYWNN.json  – 周报
    
    本地 cold_cache/ 提供离线访问能力。
    """

    def __init__(self, token: str = GITHUB_TOKEN, gist_id: str = GIST_ID_ENV) -> None:
        ensure_dirs()
        self.token    = token
        self.gist_id  = gist_id
        self.cache    = BRAIN_DIR / "cold_cache"
        self.cfg_path = BRAIN_DIR / "cloud_config.json"
        if not self.gist_id and self.cfg_path.exists():
            try:
                self.gist_id = json.loads(self.cfg_path.read_text()).get("gist_id", "")
            except Exception:
                pass

    # ── 初始化 ──

    def initialize_gist(self) -> Optional[str]:
        if self.gist_id:
            return self.gist_id
        if not self.token:
            print("[ColdMemory] 未配置 GITHUB_TOKEN，云端功能降级为本地缓存")
            return None
        result = github_request("POST", "https://api.github.com/gists", self.token, {
            "description": "KyloBrain – Kylopro Cloud Memory (private)",
            "public": False,
            "files": {
                "brain_manifest.json": {"content": json.dumps({
                    "agent": "KyloBrain", "version": "2.0",
                    "created": now_ts(), "layers": ["hot", "warm", "cold"],
                }, indent=2)},
                "patterns.json":     {"content": "[]"},
                "achievements.json": {"content": "[]"},
                "world_model.json":  {"content": "{}"},
            }
        })
        if result and "id" in result:
            self.gist_id = result["id"]
            self.cfg_path.write_text(json.dumps({
                "gist_id":   self.gist_id,
                "gist_url":  result.get("html_url", ""),
                "created":   now_ts(),
            }, indent=2))
            print(f"[ColdMemory] ✅ 云端大脑初始化: {self.gist_id}")
            return self.gist_id
        return None

    # ── 推送 / 拉取 ──

    def push(self, filename: str, content: Any) -> bool:
        if not self.gist_id:
            self.initialize_gist()
        content_str = (
            json.dumps(content, ensure_ascii=False, indent=2)
            if isinstance(content, (dict, list)) else str(content)
        )
        # 先写本地缓存
        (self.cache / filename).write_text(content_str, encoding="utf-8")
        if not self.gist_id or not self.token:
            return False
        result = github_request(
            "PATCH",
            f"https://api.github.com/gists/{self.gist_id}",
            self.token,
            {"files": {filename: {"content": content_str}}},
        )
        return result is not None

    def pull(self, filename: str, force_remote: bool = False) -> Optional[Any]:
        cache_path = self.cache / filename
        # 有效缓存直接返回
        if not force_remote and cache_path.exists():
            age_h = (time.time() - cache_path.stat().st_mtime) / 3600
            if age_h < COLD_CACHE_VALID_H:
                try:
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
        if not self.gist_id or not self.token:
            return None
        result = github_request(
            "GET",
            f"https://api.github.com/gists/{self.gist_id}",
            self.token,
        )
        if result and "files" in result:
            fdata = result["files"].get(filename)
            if fdata:
                s = fdata.get("content", "")
                cache_path.write_text(s, encoding="utf-8")
                try:
                    return json.loads(s)
                except Exception:
                    return {"raw": s}
        return None

    # ── 同步操作 ──

    def sync_patterns(self, warm: WarmMemory) -> bool:
        """把WARM中成功率>0.5的patterns推送到云端"""
        valuable = [
            p for p in warm.read_all("patterns")
            if p.get("success_rate", 0) > 0.5 and p.get("sample_count", 0) >= 2
        ]
        return self.push("patterns.json", valuable)

    def record_achievement(self, title: str, description: str,
                           impact: str = "medium") -> None:
        existing = self.pull("achievements.json") or []
        existing.append({
            "title": title, "description": description,
            "impact": impact, "timestamp": now_ts(),
        })
        self.push("achievements.json", existing)

    def update_world_model(self, updates: dict) -> None:
        """更新对数字世界的理解（平台、工具、用户习惯）"""
        model = self.pull("world_model.json") or {}
        model.update(updates)
        model["_last_updated"] = now_ts()
        self.push("world_model.json", model)

    def push_weekly_digest(self, digest: dict) -> bool:
        return self.push(f"weekly_{now_week()}.json", digest)

    # ── 觉醒恢复：从COLD重建WARM ──

    def get_recovery_bundle(self) -> dict:
        """拉取云端全部数据，供觉醒协议使用"""
        return {
            "patterns":     self.pull("patterns.json", force_remote=True) or [],
            "achievements": self.pull("achievements.json", force_remote=True) or [],
            "world_model":  self.pull("world_model.json", force_remote=True) or {},
        }

    # ── 同步节流 ──

    def should_sync(self) -> bool:
        flag = BRAIN_DIR / ".last_cold_sync"
        if not flag.exists():
            return True
        return (time.time() - flag.stat().st_mtime) > COLD_SYNC_INTERVAL_H * 3600

    def mark_synced(self) -> None:
        (BRAIN_DIR / ".last_cold_sync").write_text(now_ts())

    def is_connected(self) -> bool:
        return bool(self.token and self.gist_id)


# ══════════════════════════════════════════════
# 觉醒协议（三角冗余恢复）
# ══════════════════════════════════════════════

class AwakeningProtocol:
    """
    任意一层记忆丢失时的自动诊断与重建。

    层级健康检查 → 发现问题 → 从其他层恢复 → 验证恢复

    迁移唤醒流程（手机→高端设备）：
      阶段1 – 身份验证（SOUL.md哈希对比）
      阶段2 – 记忆重建（COLD → WARM → HOT）
      阶段3 – 能力热身（跑历史成功任务）
      阶段4 – 觉醒验证（三个身份问题）
      阶段5 – 全量激活
    """

    def __init__(self, hot: HotMemory, warm: WarmMemory, cold: ColdMemory) -> None:
        self.hot  = hot
        self.warm = warm
        self.cold = cold
        self._snap_dir = BRAIN_DIR / "snapshots"

    # ── 健康检查 ──

    def check_health(self) -> dict:
        hot_ok  = self.hot.path.exists() and self.hot.size_kb() > 0
        warm_ok = any((self.warm.dir / f"{c}.jsonl").exists()
                      for c in ["episodes", "patterns", "failures"])
        warm_stats = self.warm.stats()
        vector = warm_stats.get("vector", {})
        cold_ok = self.cold.is_connected()
        soul_ok = SOUL_FILE.exists()
        return {
            "hot":  hot_ok,
            "warm": warm_ok,
            "cold": cold_ok,
            "soul": soul_ok,
            "warm_records": {
                "episodes": warm_stats.get("episodes", 0),
                "patterns": warm_stats.get("patterns", 0),
                "failures": warm_stats.get("failures", 0),
            },
            "vector_ok": bool(vector.get("operational")),
            "vector": vector,
            "all_healthy": hot_ok and warm_ok and cold_ok and soul_ok,
        }

    def diagnose_and_recover(self) -> dict:
        health = self.check_health()
        actions = []

        if not health["hot"] and health["warm"]:
            self._recover_hot_from_warm()
            actions.append("HOT从WARM重建")

        if not health["warm"] and health["cold"]:
            bundle = self.cold.get_recovery_bundle()
            self.warm.rebuild_from_cold(bundle)
            actions.append("WARM从COLD重建")

        if not health["hot"] and not health["warm"] and health["soul"]:
            self._recover_identity_from_soul()
            actions.append("身份从SOUL.md重建")

        return {"health_before": health, "actions": actions,
                "health_after": self.check_health()}

    def _recover_hot_from_warm(self) -> None:
        recent = self.warm.read_recent("episodes", days=7)
        success_tasks = [e["task"] for e in recent if e.get("success")][:5]
        parts = ["[RECOVERED HOT MEMORY]"]
        parts.append(f"最近成功任务: {'; '.join(success_tasks)}" if success_tasks
                     else "暂无近期成功记录")
        patterns = self.warm.read_all("patterns")
        if patterns:
            top = max(patterns, key=lambda p: p.get("success_rate", 0))
            parts.append(f"最强技能: {top['task_type']} ({top['success_rate']:.0%}成功率)")
        self.hot.write("\n".join(parts))
        print("[Awakening] HOT 已从 WARM 重建")

    def _recover_identity_from_soul(self) -> None:
        soul = SOUL_FILE.read_text(encoding="utf-8") if SOUL_FILE.exists() else ""
        devlog = DEVLOG_FILE.read_text(encoding="utf-8")[-500:] if DEVLOG_FILE.exists() else ""
        self.hot.write(
            f"[IDENTITY RECOVERED FROM SOUL]\n{soul[:800]}\n\n[RECENT DEVLOG]\n{devlog}"
        )
        print("[Awakening] 身份已从 SOUL.md 重建")

    # ── 迁移唤醒流程 ──

    def migration_checklist(self) -> dict:
        """返回迁移到新设备时的5阶段检查清单"""
        steps = []

        # 阶段1：身份验证
        soul_hash = file_hash(SOUL_FILE) if SOUL_FILE.exists() else ""
        cfg = {}
        if (BRAIN_DIR / "cloud_config.json").exists():
            try:
                cfg = json.loads((BRAIN_DIR / "cloud_config.json").read_text())
            except Exception:
                pass
        steps.append({
            "phase": 1, "name": "身份验证",
            "status": "ok" if soul_hash else "missing",
            "detail": f"SOUL.md hash: {soul_hash or 'NOT FOUND'}",
            "action": "确认 SOUL.md 与原始版本一致",
        })

        # 阶段2：记忆重建
        warm_stats = self.warm.stats()
        steps.append({
            "phase": 2, "name": "记忆重建",
            "status": "ok" if warm_stats["patterns"] > 0 else "needs_recovery",
            "detail": str(warm_stats),
            "action": "如果patterns=0，运行 awakening.diagnose_and_recover()",
        })

        # 阶段3：能力热身
        skills = list((BASE_DIR / "skills").glob("*/SKILL.md")) if (BASE_DIR / "skills").exists() else []
        steps.append({
            "phase": 3, "name": "能力热身",
            "status": "ok" if skills else "warning",
            "detail": f"发现 {len(skills)} 个 Skill",
            "action": "运行一遍历史成功任务验证 Skill 可用",
        })

        # 阶段4：觉醒验证
        questions = self._generate_identity_questions()
        steps.append({
            "phase": 4, "name": "觉醒验证",
            "status": "pending",
            "detail": "需要人工验证",
            "action": f"向 Kylo 提问：{questions}",
            "questions": questions,
        })

        # 阶段5：全量激活
        cold_ok = self.cold.is_connected()
        steps.append({
            "phase": 5, "name": "全量激活",
            "status": "ready" if cold_ok else "partial",
            "detail": f"云端连接: {'✅' if cold_ok else '❌ 需配置 GITHUB_TOKEN'}",
            "action": "所有前置阶段通过后激活",
        })

        return {"steps": steps, "ready": all(s["status"] in ("ok", "pending", "ready") for s in steps[:3])}

    def _generate_identity_questions(self) -> list[str]:
        """从成就和历史中生成身份验证问题"""
        achievements = self.cold.pull("achievements.json") or []
        questions = []
        if achievements:
            a = achievements[-1]
            questions.append(f"你最近完成的成就是什么？（期望：{a.get('title', '?')}）")
        patterns = self.warm.read_all("patterns")
        if patterns:
            top = max(patterns, key=lambda p: p.get("sample_count", 0))
            questions.append(f"你最熟练的任务类型是？（期望：{top.get('task_type', '?')}）")
        questions.append("你的主人是谁？（期望：来自 SOUL.md）")
        return questions


# ══════════════════════════════════════════════
# 元认知引擎（连接三层的神经网络）
# ══════════════════════════════════════════════

class MetaCogEngine:
    """
    统一入口：把 HOT/WARM/COLD 和觉醒协议连接成一个有意识的回路。

    90% 操作不消耗 API（规则打分 + Jaccard检索）
    只有异常情况才触发 LLM 深度反省
    """

    def __init__(self) -> None:
        self.hot      = HotMemory()
        self.warm     = WarmMemory()
        self.cold     = ColdMemory()
        self.awakening = AwakeningProtocol(self.hot, self.warm, self.cold)
        ensure_dirs()

    # ── 任务前：直觉包 ──

    def pre_task_intuition(self, task: str) -> dict:
        result: dict = {
            "similar_failure": None,
            "best_pattern":    None,
            "hot_hint":        None,
            "confidence":      "unknown",
        }
        failure = self.warm.find_similar_failure(task)
        if failure:
            result["similar_failure"] = {
                "task":     failure.get("task", ""),
                "error":    failure.get("error", ""),
                "recovery": failure.get("recovery", ""),
                "warning":  "⚠️ 历史上类似任务失败过，注意规避",
            }
            result["confidence"] = "low"

        pattern = self.warm.find_best_pattern(task)
        if pattern:
            result["best_pattern"] = {
                "method":       pattern.get("method", ""),
                "success_rate": pattern.get("success_rate", 0),
                "tip": f"💡 历史成功率 {pattern.get('success_rate', 0):.0%}，建议用此方法",
            }
            result["confidence"] = "high" if pattern.get("success_rate", 0) > 0.7 else "medium"

        hot_text = self.hot.read()
        task_kws = list(tokenize(task))[:5]
        hints = [l.strip() for l in hot_text.split("\n")
                 if any(kw in l.lower() for kw in task_kws)]
        if hints:
            result["hot_hint"] = hints[:2]

        return result

    # ── 任务后：自动评分 ──

    def post_task_score(
        self, task: str, outcome: str,
        steps_taken: int, duration_sec: float,
        success: bool, errors: list[str] = None,
    ) -> dict:
        errors = errors or []
        base        = 80 if success else 20
        step_pen    = max(0, (steps_taken - 5) * 3)
        time_pen    = max(0, (duration_sec - 300) / 60) * 2
        error_pen   = len(errors) * 10
        score       = max(0, min(100, base - step_pen - round(time_pen) - error_pen))
        task_type   = self._classify_task(task)

        self.warm.record_episode(
            task=task, steps=[f"step_{i}" for i in range(steps_taken)],
            outcome=outcome, duration_sec=duration_sec,
            success=success, score=score,
        )
        self.warm.upsert_pattern(task_type, f"auto_{task_type}", success)
        if not success and errors:
            self.warm.record_failure(task, "; ".join(str(e) for e in errors))

        needs_reflection = score < 40 or (not success and len(errors) > 2)
        if needs_reflection:
            self.hot.add_entry(
                f"任务'{task[:50]}'得分异常({score})，需反省",
                category="warning"
            )

        return {
            "score":              score,
            "success":            success,
            "task_type":          task_type,
            "breakdown": {
                "base": base,
                "step_penalty":  -step_pen,
                "time_penalty":  -round(time_pen),
                "error_penalty": -error_pen,
            },
            "needs_deep_reflection": needs_reflection,
        }

    def _classify_task(self, task: str) -> str:
        t = task.lower()
        if any(w in t for w in ["代码","code","写","fix","bug","实现","编写"]): return "coding"
        if any(w in t for w in ["搜索","查找","search","find","查询"]):         return "search"
        if any(w in t for w in ["文件","file","目录","folder","读","写入"]):    return "file_ops"
        if any(w in t for w in ["发送","send","消息","message","通知","推送"]): return "communication"
        if any(w in t for w in ["分析","analyze","总结","summarize","报告"]):   return "analysis"
        if any(w in t for w in ["vscode","ide","编辑器","debug","断点"]):       return "ide_ops"
        return "general"

    # ── 记忆巩固（每日） ──

    def consolidate(self, llm_caller: Optional[Callable] = None) -> dict:
        patterns = self.warm.read_all("patterns")
        failures = self.warm.read_recent("failures", days=7)

        top_patterns = sorted(
            [p for p in patterns if p.get("sample_count", 0) >= 3],
            key=lambda p: p.get("success_rate", 0), reverse=True,
        )[:3]

        failure_groups: dict[str, list] = {}
        for f in failures:
            ft = self._classify_task(f.get("task", ""))
            failure_groups.setdefault(ft, []).append(f)
        repeat_failures = {k: v for k, v in failure_groups.items() if len(v) >= 2}

        if llm_caller and (top_patterns or repeat_failures):
            ctx = {"top_patterns": top_patterns,
                   "repeat_failures": {k: len(v) for k, v in repeat_failures.items()}}
            summary = llm_caller(
                f"用一句话总结经验规律（≤80字）：{json.dumps(ctx, ensure_ascii=False)}"
            )
        else:
            parts = []
            if top_patterns:
                b = top_patterns[0]
                parts.append(f"{b['task_type']}任务成功率{b['success_rate']:.0%}")
            if repeat_failures:
                parts.append(f"{'、'.join(repeat_failures)}类任务本周重复失败，需改进")
            summary = "经验: " + "；".join(parts) if parts else None

        if summary:
            self.hot.summarize_to_hot(summary)

        cold_synced = False
        if self.cold.should_sync():
            self.cold.sync_patterns(self.warm)
            self.cold.mark_synced()
            cold_synced = True

        return {
            "consolidated":     bool(summary),
            "summary":          summary,
            "top_patterns":     len(top_patterns),
            "repeat_failures":  list(repeat_failures.keys()),
            "cold_synced":      cold_synced,
        }

    # ── 周报 ──

    def weekly_digest(self) -> dict:
        stats    = self.warm.stats()
        episodes = self.warm.read_recent("episodes", days=7)
        patterns = self.warm.read_all("patterns")
        succ = [e for e in episodes if e.get("success")]
        fail = [e for e in episodes if not e.get("success")]
        top = sorted(patterns, key=lambda p: p.get("success_rate", 0) * p.get("sample_count", 0), reverse=True)[:5]
        digest = {
            "week": now_week(),
            "stats": {
                "total":   len(episodes),
                "success": len(succ),
                "failed":  len(fail),
                "rate":    len(succ) / len(episodes) if episodes else 0,
                "skills":  stats["patterns"],
            },
            "top_skills": [{"type": p["task_type"], "rate": p["success_rate"]} for p in top],
            "generated_at": now_ts(),
        }
        self.cold.push_weekly_digest(digest)
        return digest

    # ── 状态报告 ──

    def status(self) -> dict:
        health = self.awakening.check_health()
        return {
            "hot_kb":      round(self.hot.size_kb(), 2),
            "hot_limit_kb": round(HOT_MAX_BYTES / 1024, 2),
            "warm":        self.warm.stats(),
            "cold_ok":     self.cold.is_connected(),
            "gist_short":  self.cold.gist_id[:8] + "..." if self.cold.gist_id else None,
            "health":      health,
            "brain_dir":   str(BRAIN_DIR),
        }


# ══════════════════════════════════════════════
# nanobot Skill 接口（KyloBrainSkill）
# ══════════════════════════════════════════════

class KyloBrainSkill:
    """tools.py 注册后的统一调用入口"""

    def __init__(self) -> None:
        self.brain = MetaCogEngine()

    def _format_recall(self, params: dict) -> dict:
        query = params.get("query", "")
        collection = params.get("collection", "episodes")
        results = self.brain.warm.search(query, collection)
        mode = "vector" if self.brain.warm.vector and self.brain.warm.vector.available() else "jaccard"
        formatted = []
        for index, item in enumerate(results[:5], 1):
            formatted.append({
                "rank": index,
                "score": item.get("_score"),
                "task": item.get("task") or item.get("task_type") or item.get("content") or item.get("summary"),
                "outcome": item.get("outcome") or item.get("error") or item.get("method") or item.get("original"),
                "tags": item.get("tags", []),
            })
        return {
            "query": query,
            "collection": collection,
            "retrieval_mode": mode,
            "count": len(formatted),
            "results": formatted,
            "summary": f"已从 {collection} 中召回 {len(formatted)} 条相关记忆（模式: {mode}）。",
        }

    def handle(self, action: str, params: dict = None) -> dict:
        params = params or {}
        dispatch = {
            "pre_task":      lambda p: self.brain.pre_task_intuition(p.get("task", "")),
            "post_task":     lambda p: self.brain.post_task_score(
                task=p.get("task",""), outcome=p.get("outcome",""),
                steps_taken=p.get("steps",1), duration_sec=p.get("duration_sec",0),
                success=p.get("success",True), errors=p.get("errors",[]),
            ),
            "remember":      lambda p: self.brain.hot.add_entry(p.get("content",""), p.get("category","general")),
            "recall":        self._format_recall,
            "consolidate":   lambda p: self.brain.consolidate(),
            "weekly":        lambda p: self.brain.weekly_digest(),
            "status":        lambda p: self.brain.status(),
            "achieve":       lambda p: (self.brain.cold.record_achievement(p.get("title",""), p.get("description",""), p.get("impact","medium")), {"ok": True})[1],
            "health_check":  lambda p: self.brain.awakening.check_health(),
            "recover":       lambda p: self.brain.awakening.diagnose_and_recover(),
            "migrate":       lambda p: self.brain.awakening.migration_checklist(),
            "world_update":  lambda p: (self.brain.cold.update_world_model(p), {"ok": True})[1],
        }
        handler = dispatch.get(action)
        if not handler:
            return {"error": f"Unknown: {action}", "available": list(dispatch)}
        return handler(params)


# ══════════════════════════════════════════════
# CLI 测试
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print("🧠 KyloBrain v2.0 — 系统测试")
    print("=" * 52)

    brain = MetaCogEngine()

    print("\n[1] 云端初始化...")
    if GITHUB_TOKEN:
        gid = brain.cold.initialize_gist()
        print(f"    Gist: {gid}")
    else:
        print("    ⚠️  GITHUB_TOKEN 未配置，降级本地模式")

    print("\n[2] 系统健康检查...")
    h = brain.awakening.check_health()
    for k, v in h.items():
        print(f"    {k}: {'✅' if v else '❌'}")

    print("\n[3] 任务前直觉查询...")
    intuition = brain.pre_task_intuition("在 VS Code 里调试 Python 环境问题")
    print(f"    置信度: {intuition['confidence']}")
    print(f"    历史警告: {intuition['similar_failure']}")
    print(f"    最佳模式: {intuition['best_pattern']}")

    print("\n[4] 任务后评分...")
    score = brain.post_task_score(
        task="在 VS Code 里调试 Python 环境问题",
        outcome="找到并修复了 venv 路径问题",
        steps_taken=4, duration_sec=180, success=True,
    )
    print(f"    得分: {score['score']}/100  类型: {score['task_type']}")

    print("\n[5] 记忆巩固...")
    result = brain.consolidate()
    print(f"    摘要: {result['summary']}")

    print("\n[6] 迁移检查清单...")
    checklist = brain.awakening.migration_checklist()
    for s in checklist["steps"]:
        status_icon = {"ok":"✅","warning":"⚠️","missing":"❌","needs_recovery":"🔄","pending":"⏳","ready":"🚀","partial":"🔶"}.get(s["status"], "?")
        print(f"    Phase {s['phase']} {status_icon} {s['name']}: {s['status']}")

    print(f"\n✅ 测试完成  brain_dir={BRAIN_DIR}")
