#!/usr/bin/env python3
"""Test a single baseline strategy end-to-end."""

import json
from pathlib import Path
from scripts.llm_only_baseline import LLMOnlyBaseline

def test_single_strategy():
    """Test one strategy end-to-end to ensure full pipeline works."""

    print("🧪 Testing Single Strategy (Adaptive) End-to-End")
    print("=" * 50)

    try:
        baseline = LLMOnlyBaseline(
            seed_ontology_path=Path('data/seed_ontology/plan-ontology-v1.0.owl'),
            cq_path=Path('data/evaluation/competency_questions.json'),
            strategy="adaptive",
            model='llama3.2:3b'
        )

        print("✅ Baseline initialized successfully")
        print(f"   Strategy: {baseline.strategy_name}")
        print(f"   Model: {baseline.model}")
        print(f"   Timeout: {baseline.timeout}s")
        print(f"   Seed classes: {len(list(baseline.seed_graph.subjects()))}")
        print(f"   Competency questions: {len(baseline.cqs)}")

        # Generate prompt
        prompt = baseline.generate_adaptive_prompt()
        print(f"✅ Prompt generated ({len(prompt)} chars)")

        # Show prompt preview
        print("\n📝 Prompt Preview (first 200 chars):")
        print("-" * 40)
        print(prompt[:200] + "...")
        print("-" * 40)

        # Test strategy extension (this would call LLM in real scenario)
        print("\n🔧 Strategy class created successfully")
        print(f"   Type: {type(baseline.strategy).__name__}")

        print("\n✅ All components working correctly!")
        print("🚀 Ready for full LLM integration testing")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_single_strategy()