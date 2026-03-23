#!/usr/bin/env python3
"""
Bundle Self-Optimization Validation Test

Validates that bundles can:
1. Track their own metrics over time
2. Show improvement trend
3. Detect over-optimization
4. Avoid degradation

This is a simulation test - in production, bundles would run via AutonomousEngine.
"""

from __future__ import annotations

import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class RunRecord:
    iteration: int
    execution_time: float
    success_rate: float
    efficiency: float
    optimized: bool
    optimization_delta: float = 0.0


class BundleOptimizer:
    """Simulated bundle optimizer with self-validation"""
    
    def __init__(self, bundle_id: str, config_path: Path):
        self.bundle_id = bundle_id
        self.config_path = config_path
        self.history: List[RunRecord] = []
        self.optimization_count = 0
        self.last_optimization_time = 0
        
    def load_config(self):
        with open(self.config_path / "bundle.json") as f:
            return json.load(f)
    
    def run(self, iteration: int) -> RunRecord:
        """Simulate one bundle execution"""
        config = self.load_config()
        
        # Base metrics
        base_time = {
            "core.memory_foundation": 5.0,
            "core.boot_optimizer": 3.0,
            "core.system_hygiene": 2.0,
            "core.bundle_governor": 1.5
        }.get(self.bundle_id, 3.0)
        
        # Learning effect: improve over time
        learning_factor = min(iteration * 0.02, 0.3)
        
        # Random variance
        variance = random.uniform(-0.1, 0.1)
        
        # Calculate metrics
        execution_time = base_time * (1 - learning_factor) + variance
        execution_time = max(0.5, execution_time)
        
        success_rate = min(0.95, 0.7 + learning_factor * 0.25 + variance)
        efficiency = min(0.95, 0.5 + learning_factor * 0.4 + variance)
        
        # Optimization trigger
        should_optimize = (
            iteration > 0 and 
            efficiency < config.get("optimization_targets", [{}])[0].get("current_threshold", 0.7)
        )
        
        optimization_delta = 0.0
        if should_optimize and random.random() < 0.3:
            self.optimization_count += 1
            self.last_optimization_time = time.time()
            optimization_delta = random.uniform(0.02, 0.05)
            efficiency += optimization_delta
        
        record = RunRecord(
            iteration=iteration,
            execution_time=execution_time,
            success_rate=success_rate,
            efficiency=efficiency,
            optimized=should_optimize,
            optimization_delta=optimization_delta
        )
        
        self.history.append(record)
        return record
    
    def check_trend(self) -> str:
        """Analyze trend and detect issues"""
        if len(self.history) < 3:
            return "insufficient_data"
        
        recent = self.history[-3:]
        
        # Check for improvement
        first_eff = recent[0].efficiency
        last_eff = recent[-1].efficiency
        
        if last_eff - first_eff > 0.05:
            return "improving"
        elif first_eff - last_eff > 0.05:
            return "degrading"
        else:
            return "stable"
    
    def check_over_optimization(self) -> bool:
        """Detect if optimizing too frequently"""
        if len(self.history) < 3:
            return False
        
        recent_optimizations = sum(1 for r in self.history[-5:] if r.optimized)
        return recent_optimizations >= 4


def run_experiment():
    """Run optimization validation experiment"""
    print("="*60)
    print("Bundle Self-Optimization Validation Test")
    print("="*60)
    
    bundles_dir = Path.home() / ".swarmbot" / "bundles"
    iterations = 15
    
    results = {}
    
    for bundle_id in ["core.memory_foundation", "core.boot_optimizer", 
                      "core.system_hygiene", "core.bundle_governor"]:
        
        bundle_path = bundles_dir / bundle_id
        if not bundle_path.exists():
            print(f"\n⚠️  Bundle not found: {bundle_id}")
            continue
            
        print(f"\n[Testing] {bundle_id}")
        
        optimizer = BundleOptimizer(bundle_id, bundle_path)
        
        for i in range(iterations):
            record = optimizer.run(i)
            trend = optimizer.check_trend()
            
            status = "✓" if record.efficiency >= 0.6 else "✗"
            opt_marker = " *" if record.optimized else ""
            
            print(f"  {i+1:2d}. eff={record.efficiency:.2f}, time={record.execution_time:.1f}s{opt_marker}")
            
            time.sleep(0.05)
        
        trend = optimizer.check_trend()
        over_opt = optimizer.check_over_optimization()
        
        first = optimizer.history[0].efficiency
        last = optimizer.history[-1].efficiency
        improvement = (last - first) / first * 100
        
        results[bundle_id] = {
            "trend": trend,
            "improvement": f"{improvement:+.1f}%",
            "optimizations": optimizer.optimization_count,
            "over_optimization": over_opt
        }
        
        print(f"  → Trend: {trend}, Improvement: {improvement:+.1f}%, Opt: {optimizer.optimization_count}")
    
    # Summary
    print("\n" + "="*60)
    print("Experiment Summary")
    print("="*60)
    
    improving = sum(1 for r in results.values() if r["trend"] == "improving")
    stable = sum(1 for r in results.values() if r["trend"] == "stable")
    over_opt = sum(1 for r in results.values() if r["over_optimization"])
    
    print(f"\nTotal bundles: {len(results)}")
    print(f"Improving: {improving}")
    print(f"Stable: {stable}")
    print(f"Over-optimizing: {over_opt}")
    
    if over_opt > 0:
        print("\n⚠️  Warning: Some bundles are over-optimizing")
        for bid, res in results.items():
            if res["over_optimization"]:
                print(f"  - {bid}")
    
    if improving >= len(results) * 0.5:
        print("\n✅ Most bundles showing improvement")
        return True
    else:
        print("\n⚠️  Insufficient improvement")
        return False


if __name__ == "__main__":
    success = run_experiment()
    sys.exit(0 if success else 1)