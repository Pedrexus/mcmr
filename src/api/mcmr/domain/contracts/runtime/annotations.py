from enum import StrEnum
from typing import Annotated, Literal, TypeAliasType, get_args, get_origin

from pydantic import StringConstraints

from ....facts import Fact
from ...primitives import Unit

type OutputContract = tuple[str, str, list[str]]
type RuleId = Annotated[
    str,
    StringConstraints(pattern=r"^(?:ALL|PY|RS|TS|CPP|C|CU)-[A-Z0-9]{1,4}[0-9]{4}$"),
]


def fact_type(annotation: type | TypeAliasType) -> type[Fact]:
    """Require one concrete fact model as the first rule input."""
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    if (generic := get_origin(annotation)) is not None and generic.__name__ == "Table":
        annotation = get_args(annotation)[0]
    if not isinstance(annotation, type) or not issubclass(annotation, Fact):
        raise TypeError(f"Rule input {annotation!r} must be a Fact type")
    return annotation


def output_contract(annotation: type | TypeAliasType) -> OutputContract:
    """Resolve output kind, unit, and categories from one return annotation."""
    annotation = annotation.__value__ if isinstance(annotation, TypeAliasType) else annotation
    if get_origin(annotation) is Annotated:
        return _annotated_contract(annotation)
    origin = _generic_origin(annotation)
    if origin is not None and origin.__name__ in {"RuleQuery", "ModelQuery"}:
        return _query_contract(annotation)
    if get_origin(annotation) is Literal:
        return "category", "", [str(item) for item in get_args(annotation)]
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return "category", "", [str(item) for item in annotation]
    return annotation.__name__, "", []


def query_kind(annotation: type | TypeAliasType) -> str | None:
    """Return the relational query wrapper named by one rule annotation."""
    annotation = _annotation_value(annotation)
    origin = _generic_origin(annotation)
    name = getattr(origin, "__name__", None)
    return name if name in {"RuleQuery", "ModelQuery"} else None


def table_type(annotation: type | TypeAliasType) -> type[Fact] | None:
    """Return the concrete fact family inside one `Table` annotation, if present."""
    if get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    origin = get_origin(annotation)
    if origin is None or getattr(origin, "__name__", None) != "Table":
        return None
    return fact_type(get_args(annotation)[0])


def _annotated_contract(annotation: type) -> OutputContract:
    """Retain unit metadata while resolving the annotated value shape."""
    value, *metadata = get_args(annotation)
    unit = next((str(item) for item in metadata if isinstance(item, Unit)), "")
    output, _, categories = output_contract(value)
    return output, unit, categories


def _annotation_value(annotation: type | TypeAliasType) -> type:
    """Remove transparent aliases and annotations from one query wrapper."""
    while isinstance(annotation, TypeAliasType) or get_origin(annotation) is Annotated:
        annotation = (
            annotation.__value__
            if isinstance(annotation, TypeAliasType)
            else get_args(annotation)[0]
        )
    return annotation


def _generic_origin(annotation: type) -> type | None:
    """Return the standard or Pydantic generic origin."""
    return get_origin(annotation) or getattr(
        annotation,
        "__pydantic_generic_metadata__",
        {},
    ).get("origin")


def _query_contract(annotation: type) -> OutputContract:
    """Resolve the answer carried by one relational query wrapper."""
    arguments = get_args(annotation) or getattr(
        annotation,
        "__pydantic_generic_metadata__",
        {},
    ).get("args", ())
    return output_contract(arguments[0])
