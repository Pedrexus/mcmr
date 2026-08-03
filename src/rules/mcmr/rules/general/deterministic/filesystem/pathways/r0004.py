import polars as pl

from ...... import rule
from ......facts import DirectoryFact
from ......query import FindingQuery, OccurrenceQuery, RuleQuery
from ......table import Table


@rule("ALL-FILE0004")
def directory_pathway(subject: Table[DirectoryFact]) -> OccurrenceQuery:
    """Report a directory that only leads to one child directory.

    Definition
    ----------
    Report a directory with exactly one direct child directory and no other direct unignored file.
    A package initializer does not count as content because it states the package surface rather
    than giving the directory an independent responsibility.

    Evidence
    --------
    Each finding names the directory and records its direct file and child directory counts. The
    Boolean value is true only for a pure one-step pathway.

    Exceptions
    ----------
    A directory with a source file, configuration, guide, fixture, or second child directory has
    its own readable role and remains unreported. A source root and its top-level import package
    are structural boundaries rather than navigation steps. A language bucket under `rules` may
    lead into one `deterministic`, `contextual`, or `external` execution lane because the lane is
    part of rule selection. Git-ignored entries never reach either count.

    Examples
    --------
    Bad
    ~~~
    A `services` directory containing only `services/payments` returns `true`.

    Good
    ~~~~
    `services` containing `service.py` beside `payments` returns `false`.

    References
    ----------
    Cites "A Philosophy of Software Design", chapters 4 and 7
    """
    relations = subject
    execution_lane = pl.col("only_child_directory").is_in(
        ["deterministic", "contextual", "external"]
    ) & pl.col("path").str.split("/").list.contains(pl.lit("rules"))
    frame = relations.facts().with_columns(
        (
            (pl.col("direct_directory_count") == 1)
            & (pl.col("direct_file_count") == 0)
            & (pl.col("source_depth") > 1)
            & ~execution_lane
        ).alias("value")
    )
    return RuleQuery.boolean(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_boolean(
            frame,
            pl.col("value"),
            "directory pathway",
            evidence=pl.col("evidence"),
        ),
    )
