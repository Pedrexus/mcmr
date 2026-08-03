import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import DependencyComponentFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("ALL-ARCH0002")
def import_cycles(subject: Table[DependencyComponentFact]) -> CountQuery:
    """Count the groups of modules that import each other, directly or through a chain.

    Definition
    ----------
    Build strongly connected components from the import edges the repository graph resolved
    between modules this repository owns. Report each component holding at least two modules, plus
    any module that explicitly imports itself, as one cycle. An import of a package nobody here can
    edit is not an edge, and neither a call nor an inheritance is read.

    The unit is the component rather than the loop. A component of eight modules holds many
    distinct paths around itself, and counting those would report one tangle as dozens of findings
    that one decision resolves together. Pylint answers the other question and enumerates the
    paths, so five `R0401` messages there and one component here describe the same tangle.

    Evidence
    --------
    Each finding names the modules of one component and one import inside it, located at the file
    and line the repository states that import on. The repair is a choice, since breaking a cycle
    is an architectural decision rather than an edit anybody can prove right. The value is the
    number of cyclic components.

    Exceptions
    ----------
    None by default. A project may ignore the rule or configure an accepted maximum while it
    removes an established cycle. An import written only inside a type-checking block is not an
    edge, since it does not exist while the program runs, which is exactly the shape a project
    reaches for when it has already broken a cycle deliberately.

    Examples
    --------
    Bad
    ~~~
    `package.a` imports `package.b` while `package.b` imports `package.a`, so neither module can be
    read, tested, or moved without the other. This returns `1`. Eight modules reaching each other
    through a chain are one component and also return `1`, because one decision separates them.

    Good
    ~~~~
    Two modules that only import a common third module return `0`, and so does a repository whose
    modules never import each other.

    References
    ----------
    Generalizes Pylint R0401 cyclic-import
    Adapts Pylint C0415 import-outside-toplevel
    Cites "Clean Architecture", component coupling principles
    Cites "Large-Scale C++ Software Design", dependency cycles
    Cites "Exploring the Structure of Complex Software Designs"
    """
    relations = subject
    inside = (
        relations.records("import_edges")
        .filter(pl.col("source_component") == pl.col("target_component"))
        .sort("fact_order", "source_component", "ordinal")
    )
    members = (
        inside.select(
            "fact_id",
            pl.col("source_component").alias("component"),
            pl.concat_list("source", "target").alias("member"),
        )
        .explode("member", empty_as_null=True)
        .group_by("fact_id", "component", maintain_order=True)
        .agg(
            pl.col("member").n_unique().alias("member_count"),
            pl.col("member").unique().sort().alias("members"),
        )
    )
    components = (
        inside.group_by(
            "fact_id", pl.col("source_component").alias("component"), maintain_order=True
        )
        .agg(
            pl.len().alias("edge_count"),
            pl.col("source").first(),
            pl.col("target").first(),
            pl.col("path").first(),
            pl.col("line").first(),
            pl.col("ordinal").first(),
        )
        .join(members, on=["fact_id", "component"], how="inner")
        .join(
            relations.facts().select("fact_id", "evidence"),
            on="fact_id",
            how="inner",
        )
        .with_columns(
            pl.col("line").alias("start_line"),
            pl.lit(0, dtype=pl.UInt64).alias("start_column"),
            pl.col("line").alias("end_line"),
            pl.lit(0, dtype=pl.UInt64).alias("end_column"),
        )
    )
    facts = relations.counted(components)
    module_count = pl.concat_str(
        pl.col("member_count"),
        pl.when(pl.col("member_count") == 1).then(pl.lit(" module")).otherwise(pl.lit(" modules")),
    )
    arrow_count = pl.concat_str(
        pl.col("edge_count"),
        pl.when(pl.col("edge_count") == 1).then(pl.lit(" arrow")).otherwise(pl.lit(" arrows")),
    )
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            components,
            pl.concat_str(
                module_count,
                pl.lit(" import each other in one cycle, which are `"),
                pl.col("members").list.join("`, `"),
                pl.lit("`, and `"),
                pl.col("source"),
                pl.lit("` importing `"),
                pl.col("target"),
                pl.lit("` is one of the "),
                arrow_count,
                pl.lit(" closing it"),
            ),
            (
                ("modules in the cycle", pl.col("member_count"), Unit.COUNT),
                ("imports inside it", pl.col("edge_count"), Unit.COUNT),
            ),
            finding_order=pl.col("ordinal"),
            question=pl.concat_str(
                pl.lit("break the cycle holding `"),
                pl.col("source"),
                pl.lit("` and `"),
                pl.col("target"),
                pl.lit("`"),
            ),
            options=(
                "move what the modules share into one both can depend on",
                "invert an arrow through a contract the depended-upon module owns",
                "defer an import to the type-checking block where only a type is needed",
            ),
            evidence=pl.col("evidence"),
        ),
    )
