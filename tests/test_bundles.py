#!/usr/bin/env python3
"""
Test AutonomousEngine Bundle initialization and basic operation.
"""

import os
import sys
import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str = ""
    error: str = ""


class BundleTester:
    def __init__(self):
        self.results = []
        self.bundles_dir = Path.home() / ".swarmbot" / "bundles"
        
    def test_1_init_bundles_script(self):
        """Test: Run init_bundles.py to create bundle structure"""
        print("\n[Test 1] Bundle initialization script")
        try:
            from scripts.init_bundles import main as init_main
            init_main()
            
            core_bundles = [
                "core.memory_foundation",
                "core.boot_optimizer", 
                "core.system_hygiene",
                "core.bundle_governor"
            ]
            
            missing = []
            for bundle_id in core_bundles:
                bundle_path = self.bundles_dir / bundle_id
                if not bundle_path.exists():
                    missing.append(bundle_id)
                    
            passed = len(missing) == 0
            detail = f"Created: {len(list(self.bundles_dir.glob('*')))} bundles"
            return TestResult("Bundle initialization", passed, detail)
        except Exception as e:
            return TestResult("Bundle initialization", False, error=str(e))

    def test_2_bundle_json_structure(self):
        """Test: Verify bundle.json has proper structure"""
        print("\n[Test 2] Bundle JSON structure")
        try:
            bundle_path = self.bundles_dir / "core.boot_optimizer"
            bundle_json = bundle_path / "bundle.json"
            
            with open(bundle_json) as f:
                config = json.load(f)
            
            required_fields = ["bundle_id", "objective", "interval_seconds", 
                             "success_metrics", "constraints", "optimization_targets"]
            missing = [f for f in required_fields if f not in config]
            
            passed = len(missing) == 0
            detail = f"Fields: {list(config.keys())[:5]}..."
            
            return TestResult("Bundle JSON structure", passed, detail)
        except Exception as e:
            return TestResult("Bundle JSON structure", False, error=str(e))

    def test_3_optimization_targets(self):
        """Test: Verify optimization targets are defined"""
        print("\n[Test 3] Optimization targets")
        try:
            bundle_path = self.bundles_dir / "core.boot_optimizer"
            bundle_json = bundle_path / "bundle.json"
            
            with open(bundle_json) as f:
                config = json.load(f)
            
            targets = config.get("optimization_targets", [])
            has_targets = len(targets) > 0
            
            if has_targets:
                target = targets[0]
                has_threshold = "current_threshold" in target
                has_direction = "direction" in target
                passed = has_threshold and has_direction
                detail = f"Target: {target.get('metric_name')}, threshold: {target.get('current_threshold')}"
            else:
                passed = False
                detail = "No optimization targets"
                
            return TestResult("Optimization targets", passed, detail)
        except Exception as e:
            return TestResult("Optimization targets", False, error=str(e))

    def test_4_prevent_over_optimization(self):
        """Test: Verify anti-over-optimization mechanisms"""
        print("\n[Test 4] Anti over-optimization mechanisms")
        try:
            bundle_path = self.bundles_dir / "core.boot_optimizer"
            bundle_json = bundle_path / "bundle.json"
            
            with open(bundle_json) as f:
                config = json.load(f)
            
            constraints = config.get("constraints", [])
            feedback = config.get("feedback_loop", {})
            
            has_min_interval = any("间隔" in c or "interval" in c.lower() for c in constraints)
            has_confirm = any("确认" in c or "A/B" in c or "test" in c.lower() for c in constraints)
            
            passed = has_min_interval or has_confirm
            detail = f"Constraints: {len(constraints)}, Feedback: {feedback.get('enabled', False)}"
            
            return TestResult("Anti over-optimization", passed, detail)
        except Exception as e:
            return TestResult("Anti over-optimization", False, error=str(e))

    def test_5_bundle_governor_exists(self):
        """Test: Verify bundle_governor can manage other bundles"""
        print("\n[Test 5] BundleGovernor existence")
        try:
            governor_path = self.bundles_dir / "core.bundle_governor"
            
            has_json = (governor_path / "bundle.json").exists()
            has_run = (governor_path / "run.py").exists()
            has_eval = (governor_path / "eval_rubric.md").exists()
            
            passed = has_json and has_run and has_eval
            detail = f"json={has_json}, run={has_run}, eval={has_eval}"
            
            return TestResult("BundleGovernor structure", passed, detail)
        except Exception as e:
            return TestResult("BundleGovernor structure", False, error=str(e))

    def test_6_system_hygiene_metrics(self):
        """Test: Verify system_hygiene has proper health metrics"""
        print("\n[Test 6] System hygiene metrics")
        try:
            bundle_path = self.bundles_dir / "core.system_hygiene"
            bundle_json = bundle_path / "bundle.json"
            
            with open(bundle_json) as f:
                config = json.load(f)
            
            metrics = config.get("success_metrics", {})
            passed = len(metrics) >= 3
            detail = f"Metrics: {list(metrics.keys())}"
            
            return TestResult("System hygiene metrics", passed, detail)
        except Exception as e:
            return TestResult("System hygiene metrics", False, error=str(e))

    def run_all(self):
        print("="*60)
        print("AutonomousEngine Bundle Test Suite")
        print("="*60)
        
        self.results.append(self.test_1_init_bundles_script())
        self.results.append(self.test_2_bundle_json_structure())
        self.results.append(self.test_3_optimization_targets())
        self.results.append(self.test_4_prevent_over_optimization())
        self.results.append(self.test_5_bundle_governor_exists())
        self.results.append(self.test_6_system_hygiene_metrics())
        
        self.print_summary()
        return self.results

    def print_summary(self):
        print("\n" + "="*60)
        print("Test Summary")
        print("="*60)
        
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        
        for r in self.results:
            status = "✓" if r.passed else "✗"
            print(f"  {status} {r.name}")
            if r.detail:
                print(f"     └─ {r.detail}")
            if r.error:
                print(f"     └─ ERROR: {r.error}")
        
        print(f"\nTotal: {passed}/{total} passed")
        
        if passed == total:
            print("\n🎉 All bundle tests passed!")
        else:
            print(f"\n⚠️  {total - passed} tests failed")


def main():
    tester = BundleTester()
    tester.run_all()


if __name__ == "__main__":
    main()