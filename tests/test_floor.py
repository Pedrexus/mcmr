from mcmr.benchmark import FloorBenchmark


def test_floor_benchmark_reports_each_measured_boundary() -> None:
    report = FloorBenchmark(samples=3, fact_count=8).run()
    assert report.samples == 3
    assert report.fact_count >= 8
    assert report.rule_count == 277
    assert report.cold_discovery_nanoseconds > 0
    assert report.warm_discovery_nanoseconds > 0
    assert report.median_planning_nanoseconds > 0
    assert report.median_execution_nanoseconds > 0
    assert report.median_fix_planning_nanoseconds > 0
    assert report.median_total_nanoseconds >= report.median_execution_nanoseconds
