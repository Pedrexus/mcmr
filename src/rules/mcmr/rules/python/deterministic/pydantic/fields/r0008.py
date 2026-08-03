import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import PydanticModelFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ..relations import PydanticModelTables


@rule("PY-PYDA0008")
def implicit_arbitrary_type_model(subject: Table[PydanticModelFact]) -> CountQuery:
    """Find Pydantic models that permit arbitrary field types globally.

    Definition
    ----------
    Report every model that directly derives from `FrozenFlexModel`. Prefer `FrozenModel`, then
    mark the exact live-object boundary with Pydantic `InstanceOf` when a field holds a module,
    protocol implementation, callable service, or other arbitrary runtime type. This preserves
    validation for every ordinary field and makes the exceptional dependency visible where it is
    declared.

    Evidence
    --------
    Each finding identifies the model and the exact flexible base expression. The value is the
    number of models whose whole schema accepts arbitrary types.

    Exceptions
    ----------
    Keep a flexible base only when arbitrary values are the model's intended public data contract,
    rather than one or two injected runtime services. Projects that deliberately expose such a
    contract can disable this rule for that model's module.

    Examples
    --------
    Bad
    ~~~
    `class Catalog(FrozenFlexModel): modules: list[ModuleType]` disables schema generation for the
    whole model.

    Good
    ~~~~
    `class Catalog(FrozenModel): modules: list[InstanceOf[ModuleType]]` names and validates the
    exceptional boundary directly.

    References
    ----------
    Cites "Pydantic documentation", arbitrary types
    https://docs.pydantic.dev/latest/concepts/models/#arbitrary-types-allowed
    Cites "Pydantic documentation", InstanceOf
    https://docs.pydantic.dev/latest/concepts/validators/#special-types
    """
    tables = PydanticModelTables(subject)
    selected = (
        tables.models()
        .filter(pl.col("uses_flexible_model"))
        .sort("fact_order", "ordinal")
        .with_columns(
            pl.int_range(pl.len()).over("fact_id").alias("finding_order"),
            pl.col("flexible_base_span.path").alias("path"),
            pl.col("flexible_base_span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("flexible_base_span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("flexible_base_span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("flexible_base_span.end_column").cast(pl.UInt64).alias("end_column"),
        )
        .join(tables.facts().select("fact_id", "evidence"), on="fact_id", how="left")
    )
    frame = tables.counted(selected)
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("name"),
            pl.lit("` permits arbitrary field types through `FrozenFlexModel`"),
        ),
        (("implicit arbitrary type model", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("finding_order"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
