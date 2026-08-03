import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-CLAS0009")
def duplicate_component_attribute_alias_count(
    subject: Table[ClassFact],
) -> CountQuery:
    """Keep retained components as the single source of truth for their attributes.

    Definition
    ----------
    Inspect class constructors and Pydantic `model_post_init` methods. When an owner retains a
    parameter as one field, report other fields assigned directly from attributes of that same
    parameter. `self.document = document` followed by `self.path = document.path` creates two
    access paths for one fact and lets later changes drift. Keep `self.document` and read
    `self.document.path` where needed.

    Evidence
    --------
    Each finding identifies the retained component, copied attribute, alias field, class, and exact
    assignment range. The result is the number of direct forwarded aliases. The value is the number
    of fields assigned directly from an attribute of a retained component.

    Exceptions
    ----------
    Derived values such as `self.name = normalize(document.path.name)` are not direct aliases.
    Extracting a field is accepted when the owner does not retain the source component. Dynamic
    assignments, properties, descriptors, and nested helper scopes are not guessed.

    Examples
    --------
    Bad
    ~~~
    `self.document = document` followed by `self.path = document.path` duplicates composition
    state.

    Good
    ~~~~
    Store only `self.document = document` and use `self.document.path`. If only the path is needed,
    store `self.path = document.path` without retaining the whole document.

    References
    ----------
    Adapts Pylint R0902 too-many-instance-attributes
    Cites "A Philosophy of Software Design", chapter 5, information hiding
    Cites "Pydantic documentation", faux immutability
    https://docs.pydantic.dev/latest/concepts/models/#faux-immutability
    """
    facts = subject.lazy(ClassRelation.FACTS)
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.CLASSES)
        .filter(pl.col("duplicate_component_alias_count") > 0)
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.col("duplicate_component_alias_count").sum().alias("value"),
        pl.len().cast(pl.UInt64).alias("finding_count"),
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0),
        pl.col("finding_count").fill_null(0),
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
                pl.lit("` copies "),
                pl.col("duplicate_component_alias_count"),
                pl.lit(" attributes from a component it already retains"),
            ),
            (
                (
                    "duplicate component attribute alias count",
                    pl.col("duplicate_component_alias_count"),
                    Unit.COUNT,
                ),
            ),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
