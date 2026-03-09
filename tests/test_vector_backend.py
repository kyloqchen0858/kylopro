"""KyloBrain vector backend smoke test."""

import importlib
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "kylobrain"))

def test_vector_backend_smoke(tmp_path) -> None:
    os.environ["KYLOPRO_DIR"] = str(tmp_path)
    (tmp_path / "brain").mkdir(parents=True, exist_ok=True)
    cloud_brain = importlib.import_module("cloud_brain")
    cloud_brain = importlib.reload(cloud_brain)
    WarmMemory = cloud_brain.WarmMemory
    warm = WarmMemory()
    stats = warm.stats()
    assert "vector_enabled" in stats

    warm.record_episode(
        task="修复中文编码读取问题",
        steps=["read_file", "fallback_gbk"],
        outcome="成功读取桌面 txt 内容",
        duration_sec=1.0,
        success=True,
    )

    results = warm.search("中文编码问题", "episodes", top_k=3)
    assert isinstance(results, list)
    assert results
    if stats["vector_enabled"]:
        direct_results = warm.vector.search("episodes", "中文编码问题", top_k=3)
        assert direct_results
        assert "_score" in direct_results[0]
        assert any("_score" in row for row in results)