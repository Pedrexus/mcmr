import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import InteropFact
from .....query import FindingQuery, OccurrenceQuery, RuleQuery
from .....table import Table
from .relations import InteropTables


@rule("ALL-BIND0001")
def unreached_cross_language_artifact(subject: Table[InteropFact]) -> OccurrenceQuery:
    """Report an artifact one language declares that no other language reaches.

    Definition
    ----------
    Report a binary, native module, shared library, or kernel a repository declares where nothing
    outside its own language names it. Such an artifact is either dead weight that still has to be
    built, released, and kept compiling, or a seam whose other side was never wired. Both cost, and
    neither is visible in an import graph, because the caller and the callee never share one.

    Evidence
    --------
    Each finding names the artifact, the mechanism it is reached through, the manifest or source
    that declares it, and every file that names it. The result reports whether the artifact stands
    unreached.

    Exceptions
    ----------
    A published binary, a library another repository consumes, and a plugin a host loads at
    runtime all have their callers outside this tree. A project excludes what it ships rather than
    deleting it. A name reached only through a variable this scan cannot follow also reads as
    unreached, which is why the finding names the files it did see.

    Examples
    --------
    A Cargo manifest declaring `mcmr-kernel` that Python spawns is reached and passes. The same
    binary with no Python caller left after a refactor is reported.

    References
    ----------
    Cites "PyO3 user guide", building and distributing a module
    https://pyo3.rs/latest/building-and-distribution.html
    Cites "pybind11 documentation", module creation
    https://pybind11.readthedocs.io/en/stable/reference.html
    Cites "Python Packaging User Guide", entry points and console scripts
    https://packaging.python.org/en/latest/specifications/entry-points/
    """
    relations = InteropTables(subject)
    reached = (
        relations.crossings()
        .select("fact_id")
        .unique()
        .with_columns(pl.lit(True).alias("reached"))
    )
    frame = (
        relations.facts()
        .join(reached, on="fact_id", how="left")
        .with_columns(pl.col("reached").fill_null(False))
    )
    value = ~pl.col("reached")
    findings = FindingQuery.build(
        frame,
        pl.concat_str(
            pl.col("mechanism"),
            pl.lit(" `"),
            pl.col("name"),
            pl.lit("` is declared in "),
            pl.col("declared_language"),
            pl.lit(" but no other language reaches it"),
        ),
        (("crossing languages", pl.lit(0), Unit.COUNT),),
        predicate=value,
        evidence=pl.col("evidence"),
    )
    return RuleQuery.boolean(frame, value, findings=findings)
