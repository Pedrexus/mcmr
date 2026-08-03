import polars as pl

from ...... import rule
from ......facts import TypeAnnotationFact
from ......query import CountQuery
from ......table import Table
from ..relations import TypeAnnotationTables, count_query


@rule("PY-TYPE0004")
def prohibited_annotation(
    subject: Table[TypeAnnotationFact],
    *,
    prohibited: tuple[str, ...] = ("Any", "object"),
) -> CountQuery:
    """Count prohibited universal types in every Python annotation position.

    Definition
    ----------
    Inspect function parameters and returns, annotated variables and attributes, PEP 695 and
    explicit `TypeAlias` values, generic bases, type-parameter bounds and defaults, nested
    generic arguments, string annotations, and type comments. Resolve direct and aliased imports
    from `typing`, `typing_extensions`, and `builtins`. Bare `object` resolves to the built-in
    unless a lexical binding conservatively shadows it. Each prohibited occurrence contributes
    one to the result. Configure any subset of `Any` and `object` through `prohibited`.

    Evidence
    --------
    Each finding identifies the resolved universal type and the annotation source line. Nested
    occurrences remain separate evidence because each can require a different replacement. The
    value is the number of prohibited universal types across every annotation position.

    Exceptions
    ----------
    Unresolved names, wildcard imports, and names with another binding in the same lexical scope
    are not reported. Values outside annotation positions are ignored. External stub boundaries
    can disable one prohibition or the complete rule when their published contract requires it.

    Examples
    --------
    Bad
    ~~~
    `from typing import Any as Dynamic`, `payload: list[Dynamic]`, `value: object`, and
    `class Adapter(Protocol[Any])` contain prohibited universal types.

    Good
    ~~~~
    `payload: Mapping[str, JsonValue]` describes a capability. After `object = DomainRoot`,
    `value: object` is conservatively treated as the project type rather than the built-in.

    References
    ----------
    Cites "Python typing specification", `Any`
    https://typing.python.org/en/latest/spec/concepts.html#the-any-type
    Cites "The Python Standard Library", `object`
    https://docs.python.org/3/library/functions.html#object
    Generalizes Ruff ANN401 any-type
    https://docs.astral.sh/ruff/rules/any-type/
    Cites "Pyright documentation", advanced type concepts on `Unknown` and `Any`
    https://github.com/microsoft/pyright/blob/main/docs/type-concepts-advanced.md
    """
    relations = TypeAnnotationTables(subject)
    selected = relations.annotation_values("resolved_names").filter(
        pl.col("string_value").str.split(".").list.last().is_in(list(prohibited))
    )
    return count_query(relations, selected, "prohibited annotation")
