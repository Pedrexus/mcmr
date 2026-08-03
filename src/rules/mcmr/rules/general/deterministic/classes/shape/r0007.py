import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("ALL-CLAS0003", policy=Numeric(maximum=10))
def public_method_count(subject: Table[ClassFact]) -> CountQuery:
    """Measure the widest public callable surface one type in this module declares.

    Definition
    ----------
    Count the callables one type declares in its own body whose resolved visibility is public and
    whose name a language does not reserve for its own protocol. Return the largest count any type
    in this module reaches, so the module is judged by its widest type rather than by an average
    that a file full of small helpers would hide. Inherited members do not count, because the
    surface a reader has to learn when opening this file is the one written here.

    Every language that declares members inside a type takes part. A provider maps its own spelling
    onto the shared visibility, so a Java `public` method, a Rust `pub fn` in an `impl` block, a
    TypeScript member that is neither `private` nor `#`-prefixed, and a Python name without a
    leading underscore are all counted the same way. A constructor, an operator, and a Python
    dunder are protocol names rather than surface a caller chooses to use, so they stay out.

    The count is the measurement and a project policy owns the ceiling. A repository facade and a
    value object sit at opposite ends of what is reasonable, and only a project can say which one
    it is looking at.

    Evidence
    --------
    Each finding records the class range and every counted member with its kind and visibility. The
    value is the number of public callables the widest type in this module declares.

    Exceptions
    ----------
    Data members are counted by the neighbouring field rule rather than here. Properties and
    cached properties are attribute access rather than call sites, so they do not inflate the
    callable surface. A wide record and a wide interface stay two different findings with two
    different repairs. A module that declares no type at all measures zero rather than being
    skipped, which keeps the value comparable across every file in a repository.

    Examples
    --------
    A class declaring `open`, `read`, `close`, `__init__`, `__repr__`, and `_reset` returns `3`,
    since the two dunders are protocol names and `_reset` is not public. The same three methods
    split across two classes in one module return `2` and `1`, and the module measures `2`.

    References
    ----------
    Generalizes Pylint R0904 too-many-public-methods
    https://pylint.readthedocs.io/en/stable/user_guide/messages/refactor/too-many-public-methods.html
    Generalizes Ruff PLR0904 too-many-public-methods
    https://docs.astral.sh/ruff/rules/too-many-public-methods/
    Generalizes SonarSource S1448
    https://rules.sonarsource.com/python/RSPEC-1448/
    Cites "Clean Code", chapter 10, classes should be small
    """
    facts = subject.lazy(ClassRelation.FACTS)
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    public_methods = subject.lazy(ClassRelation.METHODS).filter(
        ~pl.col("kind").is_in(["field", "property"])
        & (pl.col("visibility") == "public")
        & ~pl.col("is_protocol_name")
    )
    method_counts = public_methods.group_by("class_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("amount"),
        pl.col("name").sort_by("ordinal").alias("method_names"),
    )
    classes = (
        subject.lazy(ClassRelation.CLASSES)
        .join(method_counts, on="class_id", how="left")
        .with_columns(
            pl.col("amount").fill_null(0),
            pl.col("method_names").fill_null(pl.lit([], dtype=pl.List(pl.String))),
        )
    )
    maximums = classes.group_by("fact_id", maintain_order=True).agg(
        pl.col("amount").max().alias("value")
    )
    selected = (
        classes.join(maximums, on="fact_id", how="inner")
        .filter(pl.col("amount") == pl.col("value"))
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    finding_counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("finding_count")
    )
    frame = (
        facts.join(maximums, on="fact_id", how="left")
        .join(finding_counts, on="fact_id", how="left")
        .with_columns(
            pl.col("value").fill_null(0),
            pl.col("finding_count").fill_null(0),
        )
    )
    method_names = pl.concat_str(
        pl.lit("`"),
        pl.col("method_names").list.join("`, `"),
        pl.lit("`"),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        finding_count=pl.col("finding_count"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` declares "),
                pl.col("amount"),
                pl.lit(" public methods"),
                pl.when(pl.col("method_names").list.len() > 0)
                .then(pl.concat_str(pl.lit(" named "), method_names))
                .otherwise(pl.lit("")),
            ),
            (("public method count", pl.col("amount"), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
