import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import TypeAnnotationFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ..relations import TypeAnnotationTables


@rule("PY-TYPE0002")
def nullable_boolean_annotation(subject: Table[TypeAnnotationFact]) -> CountQuery:
    """Find Boolean annotations that use `None` as a third state.

    Definition
    ----------
    Inspect parameter, return, variable, and type-alias annotations. Report an exact union of
    `bool` and `None`, including `bool | None`, `None | bool`, `Optional[bool]`, and
    `Union[bool, None]`. A Boolean should represent two states. A real third state should use a
    named enum or a separate presence model whose meaning is explicit.

    Evidence
    --------
    Each finding points to the nullable Boolean union. Broader JSON or scalar unions that happen to
    contain both `bool` and `None` are not treated as three-state Booleans. The value is the number
    of nullable Boolean annotations.

    Exceptions
    ----------
    External protocol signatures may require a nullable Boolean. Such adapters can disable the
    rule at that boundary while keeping the internal domain explicit.

    Examples
    --------
    `approved: bool | None` is ambiguous because `None` could mean unknown, absent, or not yet
    evaluated. `approved: bool` is two-state. `status: ApprovalStatus` names the third state.

    References
    ----------
    Cites "Python typing specification", optional types
    https://typing.python.org/en/latest/spec/special-types.html#none
    Cites "Python typing specification", enum literal states
    https://typing.python.org/en/latest/spec/literal.html#interactions-with-enums-and-exhaustiveness-checks
    """
    relations = TypeAnnotationTables(subject)
    selected = (
        relations.annotation_values("union_members")
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(
            pl.col("string_value").n_unique().alias("member_count"),
            (pl.col("string_value") == "bool").any().alias("has_bool"),
            (pl.col("string_value") == "None").any().alias("has_none"),
        )
        .filter(pl.col("has_bool") & pl.col("has_none") & (pl.col("member_count") == 2))
        .join(
            relations.annotations(),
            left_on=("fact_id", "parent_id"),
            right_on=("fact_id", "record_id"),
        )
        .filter(~pl.col("is_external_boundary"))
    )
    counted = relations.counted(selected)
    value = pl.col("value")
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("nullable Boolean annotation `"),
            pl.col("node.text"),
            pl.lit("`"),
        ),
        (("nullable boolean annotation", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("ordinal"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(
        counted,
        value,
        value,
        findings=findings,
    )
