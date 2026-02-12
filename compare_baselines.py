#!/usr/bin/env python3
"""Run comprehensive baseline comparison."""

import json
import time
from pathlib import Path
from typing import Dict, Any
from scripts.llm_only_baseline import LLMOnlyBaseline

def run_baseline_comparison():
    """Run all baseline strategies and compare results."""
    
    strategies = ["naive", "modular", "iterative", "adaptive"]
    results = {}
    
    print("🚀 Running Baseline Strategy Comparison")
    print("=" * 50)
    
    for strategy in strategies:
        print(f"\n🎯 Testing: {strategy.upper()}")
        print("-" * 30)
        
        try:
            start_time = time.time()
            
            baseline = LLMOnlyBaseline(
                seed_ontology_path=Path('data/seed_ontology/plan-ontology-v1.0.owl'),
                cq_path=Path('data/evaluation/competency_questions.json'),
                strategy=strategy,
                model='llama3.2:3b'
            )
            
            # Get prompt info
            if strategy == "iterative":
                prompts = baseline.generate_iterative_prompts()
                prompt_info = {
                    "count": len(prompts),
                    "avg_length": sum(len(p) for p in prompts) / len(prompts) if prompts else 0,
                    "total_length": sum(len(p) for p in prompts)
                }
            else:
                if strategy == "naive":
                    prompt = baseline.generate_naive_prompt()
                elif strategy == "modular":
                    prompt = baseline.generate_modular_prompt()
                elif strategy == "adaptive":
                    prompt = baseline.generate_adaptive_prompt()
                
                prompt_info = {
                    "count": 1,
                    "length": len(prompt)
                }
            
            init_time = time.time() - start_time
            
            results[strategy] = {
                "status": "success",
                "init_time": round(init_time, 2),
                "timeout": baseline.timeout,
                "prompt_info": prompt_info,
                "seed_classes": len(list(baseline.seed_graph.subjects())),
                "cq_count": len(baseline.cqs)
            }
            
            print(f"✅ Strategy: {strategy}")
            print(f"   Init time: {init_time:.2f}s")
            print(f"   Timeout: {baseline.timeout}s")
            if strategy == "iterative":
                print(f"   Prompts: {prompt_info['count']} ({prompt_info['avg_length']:.0f} avg chars)")
            else:
                print(f"   Prompt length: {prompt_info['length']} chars")
            
        except Exception as e:
            results[strategy] = {
                "status": "error",
                "error": str(e)
            }
            print(f"❌ Strategy {strategy} failed: {e}")
    
    # Save detailed results
    with open('baseline_comparison.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary table
    print("\n📊 BASELINE STRATEGY COMPARISON")
    print("=" * 60)
    print(f"{'Strategy':<12} {'Status':<8} {'Init Time':<10} {'Prompts':<8} {'Timeout':<8}")
    print("-" * 60)
    
    for strategy in strategies:
        result = results[strategy]
        if result["status"] == "success":
            prompt_count = result["prompt_info"]["count"]
            init_time = f"{result['init_time']}s"
            timeout = f"{result['timeout']}s"
            print(f"{strategy:<12} {'✅':<8} {init_time:<10} {prompt_count:<8} {timeout:<8}")
        else:
            print(f"{strategy:<12} {'❌':<8} ERROR{'':<18}")
    
    print(f"\n📁 Detailed results saved to baseline_comparison.json")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS:")
    print("• naive: Traditional approach, comprehensive but potentially overwhelming")
    print("• modular: Literature-based, groups CQs by theme for better focus")
    print("• iterative: Processes themes separately, more reliable for large models")
    print("• adaptive: Lets LLM decide scope, most flexible")
    
    print("\n🎯 For large models, try 'iterative' or 'modular' first!")

if __name__ == "__main__":
    run_baseline_comparison()