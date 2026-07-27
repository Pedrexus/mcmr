from ..... import rule
from .....facts import FunctionFact


@rule
def imperative_model_input_validation(subject: FunctionFact) -> bool:
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
    return (
        subject.is_model_method
        and not subject.is_pydantic_validator
        and subject.checks_raw_input_type
        and subject.raises_validation_exception
        and subject.constructs_owner_model
    )
