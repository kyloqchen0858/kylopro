"""
KyloBrain · VectorBackend
=========================
ChromaDB-backed retrieval layer for WARM memory.

Design:
  - Keep JSONL as the source of truth.
  - Use ChromaDB only as an optional semantic index.
  - If ChromaDB or embeddings are unavailable, the caller falls back to Jaccard.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Optional


def _resolve_base_dir() -> Path:
    env_dir = os.environ.get("KYLOPRO_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()

    # skills/kylobrain/vector_backend.py -> Kylopro-Nexus/
    repo_guess = Path(__file__).resolve().parents[2]
    cwd = Path.cwd().resolve()
    home_guess = Path.home() / "Kylopro-Nexus"
    for candidate in (repo_guess, cwd, home_guess):
        if (candidate / "brain").exists() and (candidate / "skills").exists():
            return candidate
    return repo_guess


BASE_DIR = _resolve_base_dir()
VECTOR_DIR = BASE_DIR / "brain" / "vector_store"
VALID_COLLECTIONS = {
    "episodes", "patterns", "failures", "demoted", "consolidated",
    "failure_patterns", "preference",
}


class HashEmbeddingFunction:
    """Small local embedding function with Chinese-aware tokenization."""

    def __init__(self, dims: int = 256) -> None:
        self.dims = dims

    @staticmethod
    def name() -> str:
        return "kylo_hash_embedding"

    @staticmethod
    def build_from_config(config: dict) -> "HashEmbeddingFunction":
        return HashEmbeddingFunction(dims=int(config.get("dims", 256)))

    def get_config(self) -> dict:
        return {"dims": self.dims}

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def is_legacy(self) -> bool:
        return False

    def _tokens(self, text: str) -> list[str]:
        return re.findall(r"[a-zA-Z0-9_]{2,}|[\u4e00-\u9fff]", (text or "").lower())

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        tokens = self._tokens(text)
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:2], "big") % self.dims
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    def __call__(self, input):
        return [self._embed_one(text) for text in input]

    def embed_query(self, input):
        return self.__call__(input)


class VectorBackend:
    """Optional ChromaDB index for KyloBrain WARM memory."""

    def __init__(self) -> None:
        self._client = None
        self._collections: dict[str, object] = {}
        self._available = False
        self._init_error = ""
        self._last_runtime_error = ""
        self._embedding_function = None
        self._init_client()

    def _clear_runtime_error(self) -> None:
        self._last_runtime_error = ""

    def _record_runtime_error(self, exc: Exception) -> None:
        self._last_runtime_error = str(exc)

    def _init_client(self) -> None:
        try:
            import chromadb
            VECTOR_DIR.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(VECTOR_DIR))
            self._embedding_function = HashEmbeddingFunction()
            self._available = True
        except Exception as exc:
            self._available = False
            self._init_error = str(exc)

    def available(self) -> bool:
        return self._available and self._client is not None

    def status(self) -> dict:
        return {
            "available": self.available(),
            "operational": self.available() and not self._last_runtime_error,
            "store_dir": str(VECTOR_DIR),
            "error": self._init_error or None,
            "last_runtime_error": self._last_runtime_error or None,
        }

    def _get_collection(self, collection: str):
        if collection not in VALID_COLLECTIONS:
            raise ValueError(f"Unsupported vector collection: {collection}")
        if collection not in self._collections:
            kwargs = {
                "name": f"warm_{collection}",
                "metadata": {"hnsw:space": "cosine"},
            }
            if self._embedding_function is not None:
                kwargs["embedding_function"] = self._embedding_function
            self._collections[collection] = self._client.get_or_create_collection(**kwargs)
        return self._collections[collection]

    def _record_text(self, collection: str, record: dict) -> str:
        if collection == "episodes":
            parts = [record.get("task", ""), record.get("outcome", "")]
            parts.extend(record.get("steps", []))
            parts.extend(record.get("tags", []))
            return "\n".join(str(p) for p in parts if p)
        if collection == "patterns":
            return "\n".join(str(p) for p in [record.get("task_type", ""), record.get("method", "")] if p)
        if collection == "failures":
            return "\n".join(str(p) for p in [record.get("task", ""), record.get("error", ""), record.get("recovery", "")] if p)
        if collection == "failure_patterns":
            return "\n".join(str(p) for p in [record.get("error_type", ""), record.get("task", ""), record.get("fix", "")] if p)
        if collection == "preference":
            return "\n".join(str(p) for p in [record.get("key", ""), record.get("value", ""), record.get("source", "")] if p)
        if collection == "demoted":
            return str(record.get("content", ""))
        if collection == "consolidated":
            return "\n".join(str(p) for p in [record.get("summary", ""), record.get("original", "")] if p)
        return " ".join(str(v) for v in record.values() if isinstance(v, (str, int, float)))

    def upsert_record(self, collection: str, record: dict) -> bool:
        if not self.available():
            return False
        source_id = record.get("_id")
        if not source_id:
            return False
        try:
            meta = {
                "source_id": source_id,
                "collection": collection,
                "ts": float(record.get("_ts", time.time())),
            }
            self._get_collection(collection).upsert(
                ids=[source_id],
                documents=[self._record_text(collection, record)],
                metadatas=[meta],
            )
            self._clear_runtime_error()
            return True
        except Exception as exc:
            self._record_runtime_error(exc)
            return False

    def replace_collection(self, collection: str, records: list[dict]) -> bool:
        if not self.available():
            return False
        try:
            coll = self._get_collection(collection)
            existing = coll.get(include=[])
            existing_ids = existing.get("ids", []) if existing else []
            if existing_ids:
                coll.delete(ids=existing_ids)
            valid = [record for record in records if record.get("_id")]
            if not valid:
                self._clear_runtime_error()
                return True
            coll.upsert(
                ids=[record["_id"] for record in valid],
                documents=[self._record_text(collection, record) for record in valid],
                metadatas=[{
                    "source_id": record["_id"],
                    "collection": collection,
                    "ts": float(record.get("_ts", time.time())),
                } for record in valid],
            )
            self._clear_runtime_error()
            return True
        except Exception as exc:
            self._record_runtime_error(exc)
            return False

    def search(self, collection: str, query: str, top_k: int = 5, days: Optional[int] = None) -> list[dict]:
        if not self.available() or not query.strip():
            return []
        try:
            result = self._get_collection(collection).query(
                query_texts=[query],
                n_results=max(top_k * 3, top_k),
                include=["metadatas", "distances"],
            )
            ids = result.get("ids", [[]])[0]
            metas = result.get("metadatas", [[]])[0]
            dists = result.get("distances", [[]])[0]
            cutoff = time.time() - days * 86400 if days else None
            rows = []
            for source_id, meta, dist in zip(ids, metas, dists):
                ts = float((meta or {}).get("ts", 0))
                if cutoff and ts < cutoff:
                    continue
                rows.append({
                    "_id": source_id,
                    "_score": round(1.0 - float(dist), 4),
                    "_ts": ts,
                })
                if len(rows) >= top_k:
                    break
            self._clear_runtime_error()
            return rows
        except Exception as exc:
            self._record_runtime_error(exc)
            raise


_vector_instance: Optional[VectorBackend] = None


def get_vector_backend() -> VectorBackend:
    global _vector_instance
    if _vector_instance is None:
        _vector_instance = VectorBackend()
    return _vector_instance