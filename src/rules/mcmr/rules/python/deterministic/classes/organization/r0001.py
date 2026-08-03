import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0001")
def explicit_registry_name(
    subject: Table[ClassFact],
    *,
    registry_bases: set[str] | None = None,
) -> RuleQuery[bool]:
    """Detect registry classes that override their derivable class key.

    Definition
    ----------
    A class whose direct base is `Registry`, `Strategy`, `Backend`, `Provider`, or
    `Component` should use the registry key derived from its class name. A class-level
    string assignment to `name` duplicates identity and can drift from the class. The shared
    project normalizer derives the snake-case key with `inflection.underscore`.

    Evidence
    --------
    Every finding identifies the explicit class-level `name` assignment and shows the
    snake-case key that the project derives from the class name.

    Exceptions
    ----------
    Keep an override only when a documented external protocol requires a different stable wire key.
    The exception should be explicit because removing it can change configuration. `registry_bases`
    names the bases whose subclasses derive their key from the class name, so a project with its
    own registry foundation states it rather than accepting these five.

    Examples
    --------
    `class JsonBackend(Backend): name = "json_backend"` returns `true`, because the registry
    already derives `json_backend` from the class name. `class JsonBackend(Backend)` with no `name`
    assignment returns `false`. `class JsonBackend(Backend): name = "application/json"` also
    returns `true` and needs an external wire-protocol justification to keep.

    References
    ----------
    Cites "patos documentation", `Registry` auto-derived class names
    Cites "Inflection documentation", underscore
    https://inflection.readthedocs.io/en/latest/#inflection.underscore
    """
    registry_bases = (
        {"Registry", "Strategy", "Backend", "Provider", "Component"}
        if registry_bases is None
        else registry_bases
    )
    facts = subject.lazy(ClassRelation.FACTS)
    direct_bases = subject.lazy(ClassRelation.DIRECT_BASES)
    base_names = direct_bases.group_by("class_id", maintain_order=True).agg(
        pl.col("value").sort_by("ordinal").alias("direct_bases")
    )
    registry_classes = (
        direct_bases.filter(pl.col("value").str.split(".").list.last().is_in(list(registry_bases)))
        .select("class_id")
        .unique(maintain_order=True)
    )
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.CLASSES)
        .filter(pl.col("has_explicit_registry_name"))
        .join(registry_classes, on="class_id", how="inner")
        .join(base_names, on="class_id", how="inner")
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("finding_count")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("finding_count").fill_null(0)
    )
    return RuleQuery.boolean(
        frame,
        pl.col("finding_count") > 0,
        finding_count=pl.col("finding_count"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` explicitly overrides the registry name derived by `"),
                pl.col("direct_bases").list.join("`, `"),
                pl.lit("`"),
            ),
            (("explicit registry name", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
