import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import InteropFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table
from .relations import InteropTables


@rule("ALL-BIND0002", policy=Numeric(maximum=1))
def cross_language_boundary_width(subject: Table[InteropFact]) -> CountQuery:
    """Measure how many languages depend on one cross-language artifact.

    Definition
    ----------
    Count the distinct languages that name one declared artifact, excluding the language that
    declares it and the manifests that describe it. Every language on that list depends on the
    artifact's exact name, its exact interface, and its build. A seam two languages cross is a
    contract, and one that four cross is infrastructure, and it needs a stated interface, a
    version, and a test on each side rather than a name that happens to match.

    One reaching language is the ordinary purpose of an interoperability seam and is accepted by
    the default policy. The finding starts when a second language couples itself to the same
    artifact.

    Evidence
    --------
    Each finding names the artifact, its mechanism, and each language that reaches it with the
    files that do. The value is the number of reaching languages.

    Exceptions
    ----------
    A shared runtime library is meant to be reached widely, and a project raises its ceiling
    rather than splitting it. A name matched only by coincidence would inflate the count, which is
    why a reference is recorded only where the name is stated as a literal string.

    Examples
    --------
    A CUDA kernel loaded from Python and wrapped in C++ returns `2` and deserves a stated
    interface. A binary only its own tests spawn returns `0`.

    References
    ----------
    Cites "CUDA C++ Programming Guide", the runtime and driver APIs
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html
    Cites "PyO3 user guide", the Python and Rust boundary
    https://pyo3.rs/latest/
    Cites "Release It", on integration points
    """
    relations = InteropTables(subject)
    selected = (
        relations.crossings()
        .group_by("fact_id", "language", maintain_order=True)
        .agg(
            pl.col("fact_order").first(),
            pl.col("mechanism").first(),
            pl.col("name").first(),
            pl.concat_str(pl.col("path"), pl.lit(":"), pl.col("line"))
            .sort_by("ordinal")
            .alias("locations"),
            pl.col("path").sort_by("ordinal").first().alias("path"),
            pl.col("line").sort_by("ordinal").first().cast(pl.UInt64).alias("start_line"),
            pl.lit(0, dtype=pl.UInt64).alias("start_column"),
            pl.col("line").sort_by("ordinal").first().cast(pl.UInt64).alias("end_line"),
            pl.lit(0, dtype=pl.UInt64).alias("end_column"),
            pl.col("evidence").first(),
        )
    )
    selected = selected.sort("fact_order", "language").with_columns(
        pl.int_range(pl.len()).over("fact_id").cast(pl.UInt64).alias("finding_order")
    )
    frame = relations.counted(selected)
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.col("mechanism"),
            pl.lit(" `"),
            pl.col("name"),
            pl.lit("` is reached from "),
            pl.col("language"),
            pl.lit(" at `"),
            pl.col("locations").list.join("`, `"),
            pl.lit("`"),
        ),
        (("cross language boundary width", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("finding_order"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
