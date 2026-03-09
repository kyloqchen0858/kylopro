import importlib
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "kylobrain"))


def test_status_and_health_expose_vector_runtime_state(tmp_path) -> None:
    os.environ["KYLOPRO_DIR"] = str(tmp_path)
    (tmp_path / "brain").mkdir(parents=True, exist_ok=True)

    cloud_brain = importlib.import_module("cloud_brain")
    cloud_brain = importlib.reload(cloud_brain)

    engine = cloud_brain.MetaCogEngine()
    engine.warm.record_episode(
        task="修复中文编码读取问题",
        steps=["read_file", "fallback_gbk"],
        outcome="成功读取桌面 txt 内容",
        duration_sec=1.0,
        success=True,
    )

    status = engine.status()
    health = engine.awakening.check_health()

    assert "warm" in status
    assert "vector" in status["warm"]
    assert status["warm"]["retrieval_mode"] in {"vector", "jaccard"}
    assert "operational" in status["warm"]["vector"]
    assert "last_runtime_error" in status["warm"]["vector"]

    assert "vector_ok" in health
    assert "vector" in health
    assert health["vector"]["retrieval_mode"] in {"vector", "jaccard"}
    assert "warm_records" in health
    assert health["warm_records"]["episodes"] >= 1
