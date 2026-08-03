import polars as pl

from ...... import rule
from ......facts import PydanticModelFact
from ......query import CountQuery
from ......table import Table
from ..relations import PydanticModelTables, count_query


@rule("PY-PYDA0001")
def single_field_model_validator(subject: Table[PydanticModelFact]) -> CountQuery:
    """Find model validators that depend on only one declared field.

    Definition
    ----------
    Inspect Pydantic `model_validator(mode="after")` methods. Report a method only when every
    direct attribute read from its instance resolves to one field declared on the same class.
    Calls through `self` and access to any non-field attribute suppress the finding. A one-field
    invariant belongs first in the field annotation through a built-in type, `Field`,
    `StringConstraints`, or an `Annotated` functional validator. Model validators remain the
    final layer for invariants that genuinely depend on the whole model.

    Evidence
    --------
    Each finding identifies the validator and its sole field. The count is the number of validators
    with enough static evidence to move down to the field layer. The value is the number of model
    validators reading exactly one declared field.

    Exceptions
    ----------
    Inherited fields and validators that delegate through instance methods are not inferred.
    Keep a model validator when hidden model state, validation context, inheritance, or a
    post-initialization side effect makes the whole instance the actual validation boundary.

    Examples
    --------
    Bad
    ~~~
    `@model_validator(mode="after")` followed by a method that only rejects an empty
    `self.name` is reported.

    Good
    ~~~~
    `name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` expresses
    the same local invariant in the schema. A model validator comparing `minimum` with
    `maximum` is retained because it reads two fields.

    References
    ----------
    Cites "Pydantic documentation", validators
    https://pydantic.dev/docs/validation/latest/concepts/validators/
    Cites "Pydantic documentation", StringConstraints
    https://pydantic.dev/docs/validation/latest/api/pydantic/types/#stringconstraints
    """
    tables = PydanticModelTables(subject)
    distinct_fields = (
        tables.values("models.validators.fields_read")
        .group_by("parent_id", maintain_order=True)
        .agg(pl.col("string_value").n_unique().alias("distinct_field_count"))
    )
    selected = (
        tables.validators()
        .join(distinct_fields, left_on="record_id", right_on="parent_id", how="left")
        .with_columns(pl.col("distinct_field_count").fill_null(0))
        .filter(
            (pl.col("kind") == "model_after")
            & pl.col("fields_read.present")
            & (pl.col("fields_read.length") > 0)
            & (pl.col("distinct_field_count") == 1)
            & ~pl.col("has_self_call")
            & ~pl.col("has_nonfield_access")
        )
    )
    return count_query(tables.counted(selected), "single field model validator")
