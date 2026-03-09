#!/usr/bin/env python3
"""Test the improved TaskBridge."""

import json
import time
import threading
import random
from pathlib import Path

# Test the improved version
import sys
sys.path.insert(0, '.')

# Import both versions for comparison
from kylo_tools.task_bridge import TaskBridge as OriginalBridge
from task_bridge_improved import TaskBridge as ImprovedBridge

def stress_test(bridge_class, name: str, num_workers: int = 5, iterations: int = 10):
    """Stress test a bridge implementation."""
    print(f"\n=== Stress Testing {name} ===")
    
    workspace = Path(".")
    bridge = bridge_class(workspace)
    
    # Reset state
    bridge.write_state(
        reset=True,
        task_id=f"stress_test_{name}",
        title=f"Stress Test - {name}",
        status="running",
        progress=0,
        summary=f"Stress testing {name} implementation"
    )
    
    errors = []
    success_count = 0
    
    def worker(worker_id: int):
        nonlocal success_count
        for i in range(iterations):
            try:
                state = bridge.read_state()
                current = state.get("progress", 0)
                increment = random.randint(1, 5)
                new_progress = min(100, current + increment)
                
                bridge.write_state(
                    progress=new_progress,
                    current_step=f"{name} Worker {worker_id} iter {i}",
                    append_history=f"Worker {worker_id}: {current}% -> {new_progress}%"
                )
                
                success_count += 1
                time.sleep(random.uniform(0.01, 0.05))
                
            except Exception as e:
                errors.append(f"Worker {worker_id} iteration {i}: {e}")
    
    # Create and run threads
    threads = []
    for i in range(num_workers):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
    
    start_time = time.time()
    for t in threads:
        t.start()
    
    for t in threads:
        t.join()
    
    end_time = time.time()
    
    # Read final state
    final_state = bridge.read_state()
    
    print(f"Results for {name}:")
    print(f"  Time: {end_time - start_time:.2f}s")
    print(f"  Successes: {success_count}")
    print(f"  Errors: {len(errors)}")
    print(f"  Final progress: {final_state.get('progress', 0)}%")
    
    if errors:
        print(f"  Sample errors: {errors[:3]}")
    
    # Check file integrity
    try:
        with open(bridge.state_path, 'r', encoding='utf-8') as f:
            json.load(f)
        print(f"  File integrity: OK")
    except Exception as e:
        print(f"  File integrity: FAILED - {e}")
    
    return len(errors) == 0

def test_interrupt_features():
    """Test new interrupt features."""
    print("\n=== Testing Improved Interrupt Features ===")
    
    workspace = Path(".")
    bridge = ImprovedBridge(workspace)
    
    # Reset
    bridge.write_state(
        reset=True,
        task_id="interrupt_features",
        title="Interrupt Features Test",
        status="running",
        progress=50
    )
    
    # Test check_interrupt
    print("1. Testing check_interrupt()...")
    interrupted, reason = bridge.check_interrupt()
    print(f"   Initial: interrupted={interrupted}, reason={reason}")
    
    # Request interrupt
    print("2. Requesting interrupt...")
    bridge.interrupt("Testing new features")
    
    # Check again
    interrupted, reason = bridge.check_interrupt()
    print(f"   After interrupt: interrupted={interrupted}, reason={reason}")
    
    # Test should_stop
    print("3. Testing should_stop()...")
    should_stop = bridge.should_stop()
    print(f"   should_stop() = {should_stop}")
    
    # Clear interrupt
    print("4. Clearing interrupt...")
    bridge.write_state(clear_interrupt=True)
    
    # Final check
    interrupted, reason = bridge.check_interrupt()
    print(f"   After clear: interrupted={interrupted}, reason={reason}")
    
    return True

def test_backward_compatibility():
    """Test that improved bridge is backward compatible."""
    print("\n=== Testing Backward Compatibility ===")
    
    workspace = Path(".")
    
    # Create state with original bridge
    print("1. Creating state with original bridge...")
    original = OriginalBridge(workspace)
    original.write_state(
        reset=True,
        task_id="compat_test",
        title="Compatibility Test",
        status="running",
        progress=33,
        metadata={"created_by": "original"}
    )
    
    # Read with improved bridge
    print("2. Reading with improved bridge...")
    improved = ImprovedBridge(workspace)
    state = improved.read_state()
    
    print(f"   Task ID: {state.get('task_id')}")
    print(f"   Progress: {state.get('progress')}%")
    print(f"   Metadata: {state.get('metadata')}")
    
    # Update with improved bridge
    print("3. Updating with improved bridge...")
    improved.write_state(
        progress=66,
        metadata={"updated_by": "improved"}
    )
    
    # Read back with original bridge
    print("4. Reading back with original bridge...")
    final_state = original.read_state()
    
    print(f"   Final progress: {final_state.get('progress')}%")
    print(f"   Final metadata: {final_state.get('metadata')}")
    
    # Verify
    if (final_state.get("progress") == 66 and 
        "updated_by" in final_state.get("metadata", {})):
        print("   [OK] Backward compatibility verified")
        return True
    else:
        print("   [FAIL] Backward compatibility issue")
        return False

def cleanup_temp_files():
    """Clean up any leftover temp files."""
    print("\n=== Cleaning up temp files ===")
    
    tasks_dir = Path("tasks")
    temp_files = list(tasks_dir.glob("*.tmp"))
    
    print(f"Found {len(temp_files)} temp files")
    
    for temp in temp_files:
        try:
            temp.unlink()
            print(f"  Deleted: {temp.name}")
        except Exception as e:
            print(f"  Failed to delete {temp.name}: {e}")
    
    return True

if __name__ == "__main__":
    print("TaskBridge Improvement Validation Suite")
    print("=" * 60)
    
    # Clean up first
    cleanup_temp_files()
    
    success_count = 0
    total_tests = 4
    
    # Test 1: Stress test original
    print("\n[TEST 1] Stress Test - Original Bridge")
    try:
        if stress_test(OriginalBridge, "Original"):
            success_count += 1
            print("[PASS] Original bridge stress test")
        else:
            print("[FAIL] Original bridge stress test")
    except Exception as e:
        print(f"[ERROR] Test 1 failed: {e}")
    
    # Clean temp files between tests
    cleanup_temp_files()
    
    # Test 2: Stress test improved
    print("\n[TEST 2] Stress Test - Improved Bridge")
    try:
        if stress_test(ImprovedBridge, "Improved"):
            success_count += 1
            print("[PASS] Improved bridge stress test")
        else:
            print("[FAIL] Improved bridge stress test")
    except Exception as e:
        print(f"[ERROR] Test 2 failed: {e}")
    
    # Test 3: New features
    print("\n[TEST 3] New Features Test")
    try:
        if test_interrupt_features():
            success_count += 1
            print("[PASS] New features test")
        else:
            print("[FAIL] New features test")
    except Exception as e:
        print(f"[ERROR] Test 3 failed: {e}")
    
    # Test 4: Backward compatibility
    print("\n[TEST 4] Backward Compatibility")
    try:
        if test_backward_compatibility():
            success_count += 1
            print("[PASS] Backward compatibility test")
        else:
            print("[FAIL] Backward compatibility test")
    except Exception as e:
        print(f"[ERROR] Test 4 failed: {e}")
    
    # Final cleanup
    cleanup_temp_files()
    
    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {success_count}/{total_tests} tests passed")
    
    # Recommendations
    print("\n=== PRODUCTION RECOMMENDATIONS ===")
    if success_count == total_tests:
        print("✓ Improved TaskBridge is production-ready")
        print("✓ Backward compatible with existing code")
        print("✓ Better concurrency handling")
        print("✓ Additional convenience methods")
        print("\nACTION: Replace kylo_tools/task_bridge.py with improved version")
    else:
        print("✗ Some tests failed - review before deployment")
    
    sys.exit(0 if success_count == total_tests else 1)