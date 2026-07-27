from ..... import rule
from .....facts import PydanticModelFact
from .....models import Count


@rule
def optional_variant_discriminated_union_candidate(
    subject: PydanticModelFact, *, minimum_variants: int = 2
) -> Count:
    """Find optional-field models whose validator proves mutually exclusive variants.

    Definition
    ----------
    Inspect recognized Pydantic and house model classes. Report only an imported
    `@model_validator(mode="after")` whose validation branch raises `ValueError` or
    `PydanticCustomError` when a builtin `sum` of disjoint field-presence predicates exceeds one.
    Every referenced field must have an optional annotation and an explicit `None` default. A
    direct sum or one assigned immediately before the branch is accepted. The value is the number
    of proven model candidates.

    Evidence
    --------
    Each finding names the model, validator, exact variant field groups, variant count, and total
    participating fields. A group may combine fields with `or` when those fields form one variant.
    The finding proposes no edit because discriminator design, variant names, and the
    representation of an all-absent state remain domain decisions. The value is the number of
    models whose validator proves a closed family of variants.

    Exceptions
    ----------
    Validators with custom decorators, before or wrap mode, shadowed `sum`, arbitrary helper calls,
    generators, chained comparisons, overlapping predicates, nonoptional fields, mutable defaults,
    multiple statements in the error branch, or unrecognized error types are excluded. Cross-field
    invariants that do not encode a closed family of variants should remain validators.
    `minimum_variants` is how many mutually exclusive fields a validator has to prove before the
    shape is worth naming as a union, since two alternatives are the smallest set a discriminator
    can help with.

    Examples
    --------
    Bad
    ~~~
    Several nullable fields encode alternatives and an imperative validator reconstructs the sum
    type after parsing.

    .. code-block:: python

       class Credential(BaseModel):
           token: str | None = None
           username: str | None = None
           certificate: bytes | None = None

           @model_validator(mode="after")
           def one_variant(self):
               if sum((self.token is not None,
                       self.username is not None,
                       self.certificate is not None)) > 1:
                   raise ValueError("choose one credential")
               return self

    Good
    ~~~~
    A discriminator selects one explicit model and lets Pydantic validate only that variant.

    .. code-block:: python

       class TokenCredential(BaseModel):
           kind: Literal["token"]
           token: str

       class UserCredential(BaseModel):
           kind: Literal["user"]
           username: str

       Credential = Annotated[TokenCredential | UserCredential, Field(discriminator="kind")]

    References
    ----------
    Cites "Pydantic documentation", discriminated unions
    https://pydantic.dev/docs/validation/latest/concepts/unions/#discriminated-unions
    Cites "Pydantic documentation", model validators
    https://pydantic.dev/docs/validation/latest/concepts/validators/#model-validators
    """
    return sum(
        validator.kind == "model_after"
        and validator.proves_disjoint_optional_variants
        and validator.variant_count >= minimum_variants
        for model in subject.models
        for validator in model.validators
    )
