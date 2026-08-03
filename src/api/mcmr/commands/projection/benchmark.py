from pathlib import Path

from ...audit.benchmark import FloorBenchmark
from ..interface import app, console, readable_table


@app.command
def floor(
    *,
    samples: int = 9,
    facts: int = 1000,
    output: Path | None = None,
) -> None:
    """Measure the table catalog planner floor without repository IO.

    samples: bounded repeated measurements.
    facts: logical fact count recorded beside the fixed planner cost.
    output: optional JSON report path.
    """
    with console.status("Measuring the framework floor", spinner="dots"):
        report = FloorBenchmark(samples=samples, fact_count=facts).run()
    table = readable_table("MCMR table planner floor")
    table.add_column("Boundary")
    table.add_column("Milliseconds", justify="right")
    measurements = {
        "Cold discovery": report.cold_discovery_nanoseconds,
        "Warm discovery": report.warm_discovery_nanoseconds,
        "Median execution": report.median_execution_nanoseconds,
        "Median fix planning": report.median_fix_planning_nanoseconds,
        "Median total": report.median_total_nanoseconds,
    }
    for name, nanoseconds in measurements.items():
        table.add_row(name, f"{nanoseconds / 1_000_000:.3f}")
    console.print(table)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report.model_dump_json(indent=2) + "\n")
