from pathlib import Path

from ontology_hitl.benchmarking.aggregator import ResultsAggregator
from ontology_hitl.benchmarking.models import (
    BenchmarkResult,
    MetricScores,
    BaselineSystem,
    ReductionLevel,
)
from ontology_hitl.benchmarking.reporting import ReportGenerator


def test_results_export_and_report_render(tmp_path: Path):
    agg = ResultsAggregator(output_dir=tmp_path / "out")
    m = MetricScores()
    br = BenchmarkResult(system=BaselineSystem.COGAGENT, test_case_id="t1", reduction_level=ReductionLevel.PCT_75, metrics=m)
    agg.add_result(br)

    files = agg.export_all()
    assert (tmp_path / "out" / "master_comparison.json").exists()
    assert (tmp_path / "out" / "master_comparison.csv").exists()
    assert (tmp_path / "out" / "master_comparison.md").exists()
    assert (tmp_path / "out" / "all_results.json").exists()

    # ReportGenerator.render
    rg = ReportGenerator(output_dir=tmp_path / "reports")
    master = agg.build_master_table()
    out = rg.render(master)
    assert (tmp_path / "reports" / "master_comparison.json").exists()
    assert (tmp_path / "reports" / "master_comparison.md").exists()
