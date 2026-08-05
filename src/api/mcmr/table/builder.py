import json
from enum import StrEnum
from functools import cache
from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter, ValidationError

from ..facts import Fact
from ..kernel_tables import GenericTables
from ..kernel_tables import fact_tables as native_fact_tables
from .names import GenericRelation
from .runtime.table import Table

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ..kernel_tables import (
        CallTables,
        ClassTables,
        FunctionTables,
        ImportBindingTables,
        SyntaxTables,
    )

    type NativeTables = (
        CallTables
        | ClassTables
        | FunctionTables
        | GenericTables
        | ImportBindingTables
        | SyntaxTables
    )

_schema = TypeAdapter(dict[str, JsonValue])
_schema_list = TypeAdapter(list[dict[str, JsonValue]])


@cache
def table_schema(family: type[Fact]) -> str:
    """Compile one Pydantic fact schema into structural table metadata."""
    source = _schema.validate_python(family.model_json_schema())
    return json.dumps(_schema_node(source), separators=(",", ":"), sort_keys=True)


def _optional_schema(value: JsonValue | None) -> dict[str, JsonValue] | None:
    """Return one nested JSON schema object when this keyword carries one."""
    try:
        return _schema.validate_python(value)
    except ValidationError:
        return None


def _schema_node(source: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Discard documentation and constraints that do not shape relational storage."""
    return (
        _scalar_keywords(source)
        | _variant_keywords(source)
        | _nested_keywords(source)
        | _mapping_keywords(source)
    )


def _scalar_keywords(source: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Retain scalar schema keywords that shape a stored value."""
    return {
        name: source[name]
        for name in ("$ref", "type", "default", "const", "enum", "required")
        if name in source
    }


def _variant_keywords(source: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Compile every schema branch under its original composition keyword."""
    return {
        name: [_schema_node(variant) for variant in _schema_list.validate_python(source[name])]
        for name in ("anyOf", "oneOf", "allOf", "prefixItems")
        if name in source
    }


def _nested_keywords(source: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Compile optional item and additional-property schemas."""
    compiled: dict[str, JsonValue] = {}
    for name in ("items", "additionalProperties"):
        if (nested := _optional_schema(source.get(name))) is not None:
            compiled[name] = _schema_node(nested)
    return compiled


def _mapping_keywords(source: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Compile named property and definition schema mappings."""
    compiled: dict[str, JsonValue] = {}
    for name in ("properties", "$defs"):
        if name in source:
            fields = _schema.validate_python(source[name])
            compiled[name] = {
                field: _schema_node(_schema.validate_python(value))
                for field, value in fields.items()
            }
    return compiled


def typed_table[Family: Fact, Relation: StrEnum](
    native: NativeTables,
    *,
    family: type[Family],
    relation_type: type[Relation],
) -> Table[Family]:
    """Bind native frames to their enum-owned relation identities."""
    frames = native.frames()
    return Table(
        family=family,
        relation_type=relation_type,
        frames={relation: frames[relation.value] for relation in relation_type},
    )


def generic_table[Family: Fact](family: type[Family], native: GenericTables) -> Table[Family]:
    """Bind one schema-normalized family to the universal relations."""
    return typed_table(native, family=family, relation_type=GenericRelation)


def fact_table[Family: Fact](family: type[Family], facts: Sequence[Family]) -> Table[Family]:
    """Normalize provider facts into relational tables without filesystem access."""
    payload = f"[{','.join(fact.model_dump_json() for fact in facts)}]"
    return generic_table(
        family,
        native_fact_tables(payload, schema=table_schema(family)),
    )
