import polars as pl

from ..... import rule
from .....domain.contracts import FixSafety
from .....facts import DirectoryFact
from .....query import FindingQuery, FixQuery, OccurrenceQuery, RuleQuery
from .....table import Table


@rule("ALL-FILE0001", fix_safety=FixSafety.SAFE)
def empty_directories(
    subject: Table[DirectoryFact],
) -> OccurrenceQuery:
    """Detect empty directories after repository Git ignores.

    Definition
    ----------
    Report a directory the repository walk met that holds no unignored content. Files and
    subdirectories both count, including a placeholder or a local Git ignore file.
    An empty directory is a decision nobody finished, either a package that was emptied without
    being deleted or a placeholder whose reason nobody wrote down, and every reader who meets it
    has to work out which.

    The provider walks the tree rather than deriving directories from the files it parsed, which is
    the only way a directory holding no source can be seen at all. Version control stores files
    rather than folders, so a placeholder is itself the entry that makes an intentionally empty
    folder nonempty to this rule.

    Evidence
    --------
    Each finding names one repository-relative directory holding nothing visible, together with the
    count of content entries it holds. The result reports whether this directory is empty after
    Git ignores.

    Exceptions
    ----------
    A directory Git ignores is never scanned and its subtree is never entered, so ignored build
    trees, caches, and environments never reach this rule at all. A dotted directory the repository
    does not ignore is ordinary project layout and is judged like any other directory.

    A directory a project retains on purpose is nonempty because the placeholder inside it is an
    ordinary unignored entry. No filename vocabulary is built into discovery.

    Examples
    --------
    An empty `src/unused` directory that nothing ignores or retains returns `true`, and so does a
    `logs` directory holding only a Git-ignored `__pycache__`. An unignored empty `.workspace`
    returns `true`, a `fixtures` directory holding one `.gitkeep` returns `false` because that
    placeholder retains it, and a `tests/fixtures` directory holding one file returns `false`.

    References
    ----------
    Cites "Git documentation", gitignore patterns
    https://git-scm.com/docs/gitignore
    """
    relations = subject
    frame = relations.facts().with_columns((pl.col("entry_count") == 0).alias("value"))
    selected = frame.filter(pl.col("value"))
    rewrites = selected.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("remove-directory").alias("kind"),
        pl.col("path").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    return RuleQuery.boolean(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_boolean(
            frame,
            pl.col("value"),
            "empty directories",
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Remove the directory if it remains empty.",
            rewrites=rewrites,
        ),
    )
