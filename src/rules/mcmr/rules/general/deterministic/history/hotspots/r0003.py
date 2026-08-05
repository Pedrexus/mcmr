import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import Unit
from ......facts import Ratio, RepositoryHistoryFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import HistoryRelations, Table
from ..messages import counted_text


@rule("ALL-HIST0003")
def coupled_files_that_never_name_each_other(
    subject: Table[RepositoryHistoryFact],
    *,
    minimum_shared_commits: NonNegativeInt = 5,
    minimum_confidence: Ratio = 0.5,
    maximum_commit_files: NonNegativeInt = 30,
) -> CountQuery:
    """Count file pairs that keep changing together with no import between them.

    Definition
    ----------
    Report a pair that arrived together in at least `minimum_shared_commits` focused commits, where
    focused means no more than `maximum_commit_files` changed files. Require the pair to reach
    `minimum_confidence` of the rarer file's own focused commits and no import line in either file
    to name the other. Confidence is the share that matters rather than the raw count, because a
    file touched three hundred times shares a commit with everything by accident while one touched
    eight times and always beside the same neighbor is telling us something.

    Two files that change together are coupled whether or not the code says so. Where an import
    explains it, the structure already reported it and every other family here can see it. Where
    nothing explains it, the dependency lives in an assumption two files share, and that is the
    one kind of coupling no import graph can find.

    Evidence
    --------
    One finding is stated per unexplained pair, located at the first of the two files so a reader
    opening the report lands somewhere real. Each names both files, how many focused commits
    carried both, and each file's own commit count, because a pair nobody can name is a pair
    nobody can act on. The value is the number of unexplained pairs.

    Exceptions
    ----------
    A pair involving a test is skipped, because a test changing with the code it exercises is the
    system working rather than a defect. A sweeping commit, meaning a reformat, a mass rename, or a
    dependency bump, never votes on a pair at all, since it would couple everything it touched to
    everything else. A pair the two files genuinely share through a third module is real coupling
    that this reports honestly, and the repair is usually to name the shared thing rather than to
    merge the two files.

    A file the working tree no longer holds votes on nothing. Renames are followed forward, so a
    file arrives under the name it answers to today, but one deleted or taken apart since answers
    to no name at all and naming it would ask a reader to open what is not there.

    The import reading is lexical, so a repository where no coupled pair names any other is one
    where the reader found no imports it understands rather than one where every pair is hidden.
    That case reports nothing, the same guard a claim about unreached routes needs.

    Examples
    --------
    Bad
    ~~~
    A `serializer` and a `parser` that changed together in nine of the eleven commits either one
    saw, neither importing the other. They share a wire format that is written down nowhere, so
    every change to one silently owes a change to the other.

    Good
    ~~~~
    The same two files after the format moves into a schema both import. They still change
    together, the import now says why, and a reader who opens one is told about the other.

    References
    ----------
    Cites "Your Code as a Crime Scene", chapter 7, temporal coupling
    Cites "Software Design X-Rays", chapter 5, change coupling across architectural boundaries
    Cites "Detection of Logical Coupling Based on Product Release History", ICSM 1998
    https://ieeexplore.ieee.org/document/738508
    """
    relations = HistoryRelations(subject)
    judged = relations.coupling(maximum_commit_files).filter(
        (pl.col("shared_commit_count") >= minimum_shared_commits)
        & (
            pl.col("shared_commit_count")
            >= minimum_confidence * pl.min_horizontal("left_commit_count", "right_commit_count")
        )
    )
    counts = judged.group_by("fact_id", maintain_order=True).agg(
        (pl.col("import_reference_count") > 0).any().alias("has_named_pair"),
        (pl.col("import_reference_count") == 0).sum().cast(pl.UInt64).alias("hidden_pair_count"),
    )
    facts = relations.facts()
    frame = (
        facts.join(counts, on="fact_id", how="left")
        .with_columns(
            pl.col("has_named_pair").fill_null(False),
            pl.col("hidden_pair_count").fill_null(0),
        )
        .with_columns(
            pl.when(pl.col("has_named_pair"))
            .then(pl.col("hidden_pair_count"))
            .otherwise(0)
            .alias("value")
        )
    )
    hidden = (
        judged.filter(pl.col("import_reference_count") == 0)
        .join(
            counts.filter(pl.col("has_named_pair")).select("fact_id"),
            on="fact_id",
            how="inner",
        )
        .join(facts.select("fact_id", "evidence"), on="fact_id", how="inner")
        .with_row_index("ordinal")
        .with_columns(pl.col("left").alias("path"))
    )
    findings = FindingQuery.build(
        hidden,
        pl.concat_str(
            pl.lit("`"),
            pl.col("left"),
            pl.lit("` and `"),
            pl.col("right"),
            pl.lit("` arrived together in "),
            counted_text(pl.col("shared_commit_count"), "focused commit"),
            pl.lit(" while neither names the other, out of the "),
            pl.col("left_commit_count"),
            pl.lit(" and "),
            pl.col("right_commit_count"),
            pl.lit(" each one saw"),
        ),
        (
            ("shared commits", pl.col("shared_commit_count"), Unit.COUNT),
            ("commits the first file saw", pl.col("left_commit_count"), Unit.COUNT),
            ("commits the second file saw", pl.col("right_commit_count"), Unit.COUNT),
        ),
        finding_order=pl.col("ordinal"),
        question=pl.concat_str(
            pl.lit("find out what `"),
            pl.col("left"),
            pl.lit("` and `"),
            pl.col("right"),
            pl.lit("` both assume"),
        ),
        options=(
            "name the shared thing in a module both import",
            "import one from the other where the dependency is really one way",
        ),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
