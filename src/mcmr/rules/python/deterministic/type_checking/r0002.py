from ..... import rule
from .....facts import TypeAnnotationFact
from .....models import Count


@rule
def nullable_boolean_annotation(subject: TypeAnnotationFact) -> Count:
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
    return sum(
        set(annotation.union_members) == {"bool", "None"} for annotation in subject.annotations
    )
