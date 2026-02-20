import json
import time
import sys
from pathlib import Path
from loguru import logger

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from swarmbot.swarm.manager import SwarmManager
from swarmbot.config_manager import load_config

def run_integration_tests():
    # 1. Load Config & Init SwarmManager
    print(">>> Initializing SwarmManager for Integration Tests...")
    try:
        cfg = load_config()
        # Force log mode for visibility
        cfg.swarm.display_mode = "log"
        mgr = SwarmManager.from_swarmbot_config(cfg)
    except Exception as e:
        print(f"!!! Failed to init SwarmManager: {e}")
        return

    # 2. Load Test Suite
    suite_path = Path(__file__).parent / "test_suite.json"
    with open(suite_path, "r", encoding="utf-8") as f:
        suite = json.load(f)

    results = []
    
    print(f"\n>>> Starting Test Suite: {len(suite['tests'])} tests")
    
    for test in suite["tests"]:
        test_id = test["id"]
        name = test["name"]
        user_input = test["input"]
        expected = test.get("expected_keywords", [])
        
        print(f"\n--------------------------------------------------")
        print(f"Running Test [{test_id}]: {name}")
        print(f"Input: {user_input}")
        
        start_time = time.time()
        try:
            # Execute Swarm
            response = mgr.chat(user_input)
            duration = time.time() - start_time
            
            # Validation
            missing_keywords = [kw for kw in expected if kw.lower() not in response.lower()]
            passed = len(missing_keywords) == 0
            
            result = {
                "id": test_id,
                "passed": passed,
                "duration": f"{duration:.2f}s",
                "response_snippet": response[:100] + "...",
                "missing": missing_keywords
            }
            
            if passed:
                print(f"✅ PASSED ({duration:.2f}s)")
            else:
                print(f"❌ FAILED. Missing keywords: {missing_keywords}")
                print(f"Response: {response}")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            result = {"id": test_id, "passed": False, "error": str(e)}
            
        results.append(result)
        
        # Brief pause between tests
        time.sleep(1)

    # 3. Summary
    print("\n==================================================")
    print("TEST SUMMARY")
    print("==================================================")
    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)
    
    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"{status} [{r['id']}] {r.get('duration', 'N/A')}")
        
    print(f"\nTotal: {total}, Passed: {passed_count}, Failed: {total - passed_count}")
    
    if passed_count == total:
        print("\n🎉 ALL TESTS PASSED! Swarmbot is fully functional.")
    else:
        print("\n⚠️ SOME TESTS FAILED. Please check logs.")

if __name__ == "__main__":
    run_integration_tests()