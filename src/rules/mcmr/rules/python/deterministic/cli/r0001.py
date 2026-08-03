import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import CallRelation, Table


@rule("PY-CLI0001")
def argparse_cli_construction(subject: Table[CallFact]) -> CountQuery:
    """Count CLI parsers that bypass the configured Cyclopts foundation.

    Definition
    ----------
    Resolve module, direct, and aliased imports of `argparse.ArgumentParser`. Count each proven
    construction. The project preference is to register typed callables with `cyclopts.App`
    instead of maintaining a second command schema in parser-building code.

    Evidence
    --------
    Each finding identifies the constructor call and records both the observed and preferred CLI
    framework. Lexical assignments and parameters that shadow an import suppress the finding. The
    value is the number of proven `argparse.ArgumentParser` constructions.

    Exceptions
    ----------
    Libraries that extend an external argparse parser, compatibility shims, and generated or
    vendored code may disable this project preference. Merely importing argparse for a compatible
    formatter or namespace does not count.

    Examples
    --------
    Bad
    ~~~
    `parser = argparse.ArgumentParser()` starts a hand-maintained parser command tree.

    Good
    ~~~~
    `app.command(project.build)` exposes the typed callable as the command boundary.

    References
    ----------
    Cites "Cyclopts documentation"
    https://cyclopts.readthedocs.io/en/latest/
    Cites "The Python Standard Library", argparse
    https://docs.python.org/3/library/argparse.html
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .filter(pl.col("qualified_name") == "argparse.ArgumentParser")
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.lit(
                "`argparse.ArgumentParser` builds a second CLI schema instead of exposing typed "
                "callables through Cyclopts"
            ),
            (("argparse cli construction", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
