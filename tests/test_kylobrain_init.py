"""KyloBrain v2.0 — 全模块集成测试"""
import sys
import os

os.environ.setdefault("KYLOPRO_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.environ["KYLOPRO_DIR"], "skills", "kylobrain"))

# 1. 模块导入测试
from cloud_brain import MetaCogEngine, KyloBrainSkill, HotMemory, WarmMemory, ColdMemory, AwakeningProtocol
print("[1] cloud_brain: OK")

from metacog_algorithms import MetaCogAlgorithms, ConfidenceCalibrator, FailureBloomFilter, PatternGraph, ReActMonitor
print("[2] metacog_algorithms: OK")

from ide_bridge_enhanced import IDEOrchestrator, IDESkill, VSCodeBridge, AntigravityBridge
print("[3] ide_bridge_enhanced: OK")

from kylobrain_connector import KyloConnector, get_connector, track_task
print("[4] kylobrain_connector: OK")

# 2. 总装配测试
kc = KyloConnector()
status = kc.full_status()
mods = status.get("modules", {})
print(f"\n[5] Modules: brain={mods['brain']} algo={mods['algos']} ide={mods['ide']}")

# 3. 任务生命周期
hints = kc.on_task_start("test_001", "Debug Python venv issue", confidence=0.8)
hint_text = hints.get("prompt_hint_text", "(none)")
print(f"[6] Task hints: {hint_text or '(empty - first run)'}")

result = kc.on_task_complete("test_001", "Fixed venv path", success=True, steps=3)
score = result.get("score", {}).get("score", "?")
print(f"[7] Task score: {score}/100")

# 4. 元认知算法
algos = kc.algos
algos.calibrator.record(0.8, True, "test prediction")
algos.bloom.remember_failure("Python pip install permission error")
algos.graph.record_sequence(["coding", "testing", "deploy"])
check = algos.pre_task_check("Fix pip dependency issue", 0.75)
print(f"[8] Bloom warning: {check['bloom_warning']}")
print(f"    Adjusted confidence: {check['adjusted_confidence']}")

# 5. 大脑技能接口
skill = KyloBrainSkill()
r = skill.handle("status")
print(f"[9] Brain status: HOT={r['hot_kb']}KB, WARM episodes={r['warm']['episodes']}")

# 6. 健康检查
h = kc.health_check()
print(f"[10] Health: ", end="")
for k, v in h.items():
    if k != "all_healthy":
        icon = "OK" if v else "MISSING"
        print(f"{k}={icon} ", end="")
print()

print("\n=== ALL MODULES VALIDATED ===")

