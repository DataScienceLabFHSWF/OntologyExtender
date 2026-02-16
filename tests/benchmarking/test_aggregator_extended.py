from ontology_hitl.benchmarking.aggregator import ResultsAggregator
from ontology_hitl.benchmarking.models import (
    BenchmarkResult,
    MetricScores,
    SemanticMatchResult,
    SemanticMatchLevel,
    OWLUnitTestSuite,
    OntoURLCapabilityProfile,
    BaselineSystem,
    ReductionLevel,
)


def test_aggregator_includes_extended_metrics():
    agg = ResultsAggregator(output_dir="results/benchmarking_test")
    m = MetricScores()
    # semantic match concept: 50%
    m.semantic_match_concept = SemanticMatchResult(level=SemanticMatchLevel.CONCEPT, total_generated=2, total_matched=1, match_percentage=50.0)
    # triple: 25%
    m.semantic_match_triple = SemanticMatchResult(level=SemanticMatchLevel.TRIPLE, total_generated=4, total_matched=1, match_percentage=25.0)
    # OWLUnit: one passing out of one
    suite = OWLUnitTestSuite(suite_name="s1", ontology_path="/tmp/none", results=[], total_tests=0, passed_tests=0)
    m.owlunit_suite = suite
    # OntoURL profile
    m.ontourl_profile = OntoURLCapabilityProfile(overall_avg=0.73)

    br = BenchmarkResult(system=BaselineSystem.COGAGENT, test_case_id="t1", reduction_level=ReductionLevel.PCT_75, metrics=m)
    agg.add_result(br)

    master = agg.build_master_table()
    cog = master.get("cogagent")
    assert cog is not None
    assert "semantic_match_concept" in cog
    assert abs(cog["semantic_match_concept"] - 0.5) < 1e-6
    assert abs(cog["semantic_match_triple"] - 0.25) < 1e-6
    assert "owlunit_pass_rate" in cog
    assert "ontourl_overall" in cog
    assert abs(cog["ontourl_overall"] - 0.73) < 1e-6
