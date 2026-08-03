import polars as pl

from ...... import rule
from ......facts import FunctionFact
from ......query import FindingQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("PY-PYDA0003")
def imperative_model_input_validation(subject: Table[FunctionFact]) -> RuleQuery[bool]:
    """Find model factories that manually reproduce Pydantic field validation.

    Definition
    ----------
    Inspect classes derived from Pydantic or configured house model bases. Report a non-validator
    method only when it checks raw factory input with `isinstance`, raises a validation-shaped
    exception, and constructs the enclosing model. Field annotations, nested model types,
    constrained `Annotated` aliases, `Field`, `ConfigDict(extra="forbid")`, and Pydantic field or
    model validators should own this work. A thin factory that only calls `model_validate` is
    accepted.

    Evidence
    --------
    Each finding identifies the model and factory method. Pydantic then retains nested field paths,
    aggregates independent failures, and raises one structured `ValidationError` to the caller.

    Exceptions
    ----------
    Boundary code may validate data that is not model input. A model validator may inspect raw
    input when field declarations cannot express an invariant. Validator code should raise
    `ValueError` or `PydanticCustomError`, not construct `ValidationError` directly.

    Examples
    --------
    Bad
    ~~~
    A `from_table` method checks that `judgments` is a list, checks every item is a dictionary,
    rejects unknown keys, and then calls `cls(...)`.

    Good
    ~~~~
    `judgments: list[BackendConfiguration]` validates the nested collection automatically and
    `ConfigDict(extra="forbid")` rejects unknown keys. A model validator handles only a genuine
    cross-field invariant and raises `ValueError` when it fails.

    References
    ----------
    Cites "Pydantic documentation", models, nested models, extra data, and `model_validate`
    https://pydantic.dev/docs/validation/latest/concepts/models/
    Cites "Pydantic documentation", field and model validators
    https://pydantic.dev/docs/validation/latest/concepts/validators/
    Cites "Pydantic documentation", error handling
    https://pydantic.dev/docs/validation/latest/errors/errors/
    """
    frame = subject.lazy(FunctionRelation.FUNCTIONS)
    value = (
        pl.col("is_model_method")
        & ~pl.col("is_pydantic_validator")
        & pl.col("checks_raw_input_type")
        & pl.col("raises_validation_exception")
        & pl.col("constructs_owner_model")
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "imperative model input validation"),
    )
