import polars as pl

from ...... import rule
from ......facts import PydanticModelFact
from ......query import CountQuery
from ......table import Table
from ..relations import PydanticModelTables, count_query


@rule("PY-PYDA0002")
def declarative_field_constraint_candidate(subject: Table[PydanticModelFact]) -> CountQuery:
    """Find field validators that reimplement built-in Pydantic constraints.

    Definition
    ----------
    Inspect imported Pydantic `field_validator` methods and the directly declared fields they
    target. Recognize exact string normalization with `strip`, `lower`, or `upper`, rejecting
    length comparisons, and rejecting numeric bound comparisons. Map those fragments to
    `StringConstraints` or `Field` metadata. Report only directly typed fields and literal
    comparisons whose replacement preserves the observed boundary.

    Evidence
    --------
    Each finding names the validator, its fields, and the precise declarative metadata already
    provided by Pydantic. Several fragments in one validator produce one combined finding. The
    value is the number of recognized declarative constraints across every field validator.

    Exceptions
    ----------
    Domain checks, context-dependent validation, external lookups, cross-field invariants,
    unknown type aliases, wildcard validators, and Python regular-expression semantics are not
    inferred. Keep any irreducible logic in an `Annotated` functional validator or a field
    validator after moving the recognized constraints into the type.

    Examples
    --------
    Bad
    ~~~
    A field validator returning `value.strip()` and raising when `len(value) < 1` is reported as
    `StringConstraints(strip_whitespace=True)` plus `StringConstraints(min_length=1)`.

    Good
    ~~~~
    `type NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`
    makes validation reusable, visible in the annotation, and represented in generated schema.
    A validator checking a repository or another field remains ordinary custom logic.

    References
    ----------
    Cites "Pydantic documentation", validators, reusable annotated pattern
    https://pydantic.dev/docs/validation/latest/concepts/validators/#using-the-annotated-pattern
    Cites "Pydantic documentation", types, `StringConstraints`
    https://pydantic.dev/docs/validation/latest/api/pydantic/types/#stringconstraints
    Cites "Pydantic documentation", fields, numeric and collection constraints
    https://pydantic.dev/docs/validation/latest/concepts/fields/#field-constraints
    """
    tables = PydanticModelTables(subject)
    selected = tables.validators().filter(pl.col("kind") == "field")
    return count_query(
        tables.counted(selected, pl.col("declarative_constraint_count")),
        "declarative field constraint candidate",
    )
