from ..... import rule
from .....facts import ParameterFact
from .....models import Choice, Finding, Measurement, Reported


@rule
def concrete_collection_parameter(subject: ParameterFact) -> Reported[bool]:
    """Detect concrete collection parameters that require only an abstract capability.

    Definition
    ----------
    Inspect operations performed directly on parameters annotated as `list`, variadic
    `tuple`, `dict`, or `set`. Report a broader `collections.abc` input contract only when
    all observed uses are known and non-mutating. This applies the Python convention of
    accepting the narrowest required capability while leaving concrete return types alone.

    Evidence
    --------
    Each finding names the callable, the parameter, the concrete annotation it declares, and the
    exact place the source states it, beside how many operations the body performs on it, which
    is what proves nothing needs the concrete type. An unknown call, mutation, fixed-position
    tuple, or mixed capability set suppresses the finding instead of guessing. The repair is a
    choice between the protocols the body could have asked for.

    Exceptions
    ----------
    Keep concrete types at serialization, C-extension, framework, dispatch, hashing, and other
    exact representation boundaries. Fixed heterogeneous tuples may be records, coordinates,
    protocol fields, or hash keys. Mutable parameters should retain a mutable contract.

    Examples
    --------
    `def first(values: list[int]): return values[0]` returns `true` and can accept `Sequence[int]`,
    and so does `def save(row: dict[str, str]): return row.get("id")`, which can accept
    `Mapping[str, str]`. `def add(values: list[int]): values.append(1)` returns `false`, because
    appending needs a mutable contract. A parameter whose uses the provider could not all resolve
    also returns `false`.

    References
    ----------
    Cites "Fluent Python", chapter 13, Interfaces, Protocols, and ABCs
    Cites "The Python Standard Library", `typing`, generic `Sequence` and `Mapping` parameters
    Cites "The Python Standard Library", `collections.abc` abstract methods and mixins
    """
    concrete = {"list", "tuple", "dict", "set"}
    mutating = {"append", "extend", "insert", "pop", "remove", "clear", "update", "add"}
    overspecified = [
        parameter
        for parameter in subject.parameters
        if parameter.annotation in concrete
        and parameter.all_uses_known
        and not parameter.is_return_value
        and not mutating.intersection(parameter.operations)
    ]
    return Reported(
        value=bool(overspecified),
        findings=tuple(
            Finding(
                message=(
                    f"`{parameter.owner}` declares `{parameter.name}` as a `"
                    f"{parameter.annotation}` and never does anything only a `"
                    f"{parameter.annotation}` can do"
                ),
                span=parameter.span or subject.span,
                measurements=(
                    Measurement(name="operations on it", value=len(parameter.operations)),
                    Measurement(
                        name="of them needing the concrete type",
                        value=len(mutating.intersection(parameter.operations)),
                    ),
                ),
                repair=Choice(
                    question=f"ask `{parameter.name}` for the capability the body uses",
                    options=("an iterable it walks", "a mapping or a set it only looks into"),
                ),
            )
            for parameter in overspecified
        ),
    )
