#!/usr/bin/env python3
"""Test script to run different baseline strategies."""

import json
import time
from pathlib import Path
from scripts.llm_only_baseline import LLMOnlyBaseline

def test_strategies():
    """Test all baseline strategies with a small model."""
    
    strategies = ["naive", "modular", "iterative", "adaptive"]
    results = {}
    
    for strategy in strategies:
        print(f"\n🧪 Testing strategy: {strategy}")
        
        try:
            start_time = time.time()
            
            baseline = LLMOnlyBaseline(
                seed_ontology_path=Path('data/seed_ontology/plan-ontology-v1.0.owl'),
                cq_path=Path('data/evaluation/competency_questions.json'),
                strategy=strategy,
                model='llama3.2:3b'
            )
            
            # Generate prompt to check it works
            if strategy == "naive":
                prompt = baseline.generate_naive_prompt()
            elif strategy == "modular":
                prompt = baseline.generate_modular_prompt()
            elif strategy == "iterative":
                prompts = baseline.generate_iterative_prompts()
                prompt = prompts[0] if prompts else "No prompts generated"
            elif strategy == "adaptive":
                prompt = baseline.generate_adaptive_prompt()
            
            end_time = time.time()
            
            results[strategy] = {
                "status": "success",
                "prompt_length": len(prompt),
                "init_time": end_time - start_time,
                "timeout": baseline.timeout
            }
            
            print(f"✅ {strategy}: {len(prompt)} chars, {end_time - start_time:.2f}s init")
            
        except Exception as e:
            results[strategy] = {
                "status": "error",
                "error": str(e)
            }
            print(f"❌ {strategy}: {e}")
    
    # Save results
    with open('baseline_strategy_test.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📊 Results saved to baseline_strategy_test.json")
    
    # Print summary
    print("\n📈 Strategy Comparison:")
    for strategy, result in results.items():
        if result["status"] == "success":
            print(f"  {strategy}: {result['prompt_length']} chars, {result['init_time']:.2f}s init")
        else:
            print(f"  {strategy}: ERROR - {result['error']}")

if __name__ == "__main__":
    test_strategies()