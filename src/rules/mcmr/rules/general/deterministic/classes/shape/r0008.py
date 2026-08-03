import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import SymbolReachFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ...reach.relations import ReachTables


@rule("ALL-CLAS0004", policy=Numeric(maximum=7))
def declared_field_count(subject: Table[SymbolReachFact]) -> CountQuery:
    """Measure the widest data surface one type in this module declares.

    Definition
    ----------
    Group every data member this module declares by the type that owns it and return the largest
    group. A data member is state a reader has to hold in mind for every method of the type, so the
    width of the widest type is what says whether the file asks too much. Counting is by resolved
    declaration rather than by syntax, so a name a type states once in its body and again in its
    initializer is one member, not two.

    Every language that attaches state to a type takes part, and each one spells the declaration
    differently. A Rust struct field, a TypeScript property, a C++ member, a Python class-body
    annotation, and a Python initializer assigning to `self` all arrive as the same resolved
    declaration, so one measurement covers them.

    Reading the whole module at once is what makes the measure affordable. Ownership comes from the
    qualified name each declaration already carries, so nothing has to be re-resolved and a type
    split across an interface and its implementation still counts once.

    Evidence
    --------
    Each finding records the module range and every data member grouped under the type declaring
    it. The value is the size of the largest group.

    Exceptions
    ----------
    Callables are counted by the neighbouring public-method rule, because a wide record and a wide
    interface are two different defects. A module declaring no type at all measures zero. The count
    is a measurement, and a project policy owns the ceiling, since a serialized message and a
    service object tolerate very different widths.

    Examples
    --------
    A class whose initializer assigns `self.host`, `self.port`, and `self.timeout` returns `3`, and
    a dataclass stating the same three names as annotations returns `3` as well. A class stating
    `host: str` in its body and assigning `self.host` in its initializer counts `host` once, so it
    returns `1`. A module declaring only functions returns `0`.

    References
    ----------
    Adapts Pylint R0902 too-many-instance-attributes
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-instance-attributes.html
    Cites Clippy struct_field_names
    https://rust-lang.github.io/rust-clippy/master/index.html#struct_field_names
    Generalizes SonarSource S1820
    https://rules.sonarsource.com/java/RSPEC-1820/
    Cites "Refactoring", the large class smell
    """
    relations = ReachTables(subject)
    declarations = relations.declarations()
    classes = declarations.filter(pl.col("kind") == "class").select(
        "fact_id",
        pl.col("qualname").alias("owner"),
        pl.col("span.path").alias("class_path"),
        pl.col("span.start_line").alias("class_start_line"),
        pl.col("span.start_column").alias("class_start_column"),
        pl.col("span.end_line").alias("class_end_line"),
        pl.col("span.end_column").alias("class_end_column"),
    )
    owners = (
        declarations.filter(pl.col("kind") == "attribute")
        .with_columns(pl.col("qualname").str.replace(r"(?:\.|::)[^.:]+$", "").alias("owner"))
        .group_by("fact_id", "owner", maintain_order=True)
        .agg(
            pl.len().cast(pl.UInt64).alias("width"),
            pl.col("qualname").sort().alias("fields"),
            pl.col("span.path").first().alias("field_path"),
            pl.col("span.start_line").first().alias("field_start_line"),
            pl.col("span.start_column").first().alias("field_start_column"),
            pl.col("span.end_line").first().alias("field_end_line"),
            pl.col("span.end_column").first().alias("field_end_column"),
            pl.col("evidence").first(),
        )
        .join(classes, on=["fact_id", "owner"], how="left")
        .with_columns(
            pl.coalesce("class_path", "field_path").alias("path"),
            pl.coalesce("class_start_line", "field_start_line").alias("start_line"),
            pl.coalesce("class_start_column", "field_start_column").alias("start_column"),
            pl.coalesce("class_end_line", "field_end_line").alias("end_line"),
            pl.coalesce("class_end_column", "field_end_column").alias("end_column"),
        )
    )
    widest = owners.group_by("fact_id", maintain_order=True).agg(
        pl.col("width").max().alias("value")
    )
    selected = (
        owners.join(widest, on="fact_id", how="inner")
        .filter(pl.col("width") == pl.col("value"))
        .sort("fact_id", "owner")
        .with_columns(
            pl.int_range(pl.len()).over("fact_id").cast(pl.UInt64).alias("finding_order")
        )
    )
    finding_counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("finding_count")
    )
    frame = (
        relations.facts()
        .join(widest, on="fact_id", how="left")
        .join(finding_counts, on="fact_id", how="left")
        .with_columns(
            pl.col("value").fill_null(0),
            pl.col("finding_count").fill_null(0),
        )
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        finding_count=pl.col("finding_count"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("owner"),
                pl.lit("` declares "),
                pl.col("width"),
                pl.lit(" fields named `"),
                pl.col("fields").list.join("`, `"),
                pl.lit("`"),
            ),
            (("declared field count", pl.col("width"), Unit.COUNT),),
            finding_order=pl.col("finding_order"),
            evidence=pl.col("evidence"),
        ),
    )
