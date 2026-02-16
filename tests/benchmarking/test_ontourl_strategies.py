from __future__ import annotations

from typing import Any


class DummyLLM:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        # simulate a roleplay dialogue that ends with FINAL ANSWER:
        return "Knowledge Engineer: ...\nDomain Expert: ...\nKnowledge Worker: ...\nFINAL ANSWER: ComputedAnswer"


def test_hcome_calls_llm_and_parses_final_answer() -> None:
    from ontology_hitl.benchmarking.ontourl.hcome_strategy import HCOMEStrategy

    llm = DummyLLM()
    strat = HCOMEStrategy(llm)
    example = {"question": "Define Foo class?"}

    out = strat.answer(example, "open_text", "3_1")

    assert out == "ComputedAnswer"
    assert len(llm.calls) == 1
    # prompt should include the example question (we use the shared prompt builder)
    assert "Define Foo class?" in llm.calls[0]


def test_hcome_applicable_to_true() -> None:
    from ontology_hitl.benchmarking.ontourl.hcome_strategy import HCOMEStrategy

    strat = HCOMEStrategy(DummyLLM())
    assert strat.applicable_to("mc", "1_1") is True


def test_hcome_3round_makes_three_calls_and_parses() -> None:
    from ontology_hitl.benchmarking.ontourl.hcome_strategy import HCOME3RoundStrategy

    class SeqLLM:
        def __init__(self) -> None:
            self.calls = []
            self._i = 0

        def generate(self, prompt: str, timeout: float | None = None) -> str:
            self.calls.append(prompt)
            # return different output per round
            self._i += 1
            if self._i == 1:
                return "InitialCandidate"
            elif self._i == 2:
                return "RefinedCandidate"
            else:
                return "Roleplay...\nFINAL ANSWER: FinalCandidate"

    llm = SeqLLM()
    strat = HCOME3RoundStrategy(llm)
    out = strat.answer({"question": "Define Foo"}, "open_text", "3_1")

    assert out == "FinalCandidate"
    assert len(llm.calls) == 3
    assert "Round 1" in llm.calls[0]
    assert "Round 2" in llm.calls[1]
    assert "Round 3" in llm.calls[2]
