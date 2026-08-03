from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter

if TYPE_CHECKING:
    from collections.abc import Mapping

    import polars as pl

    from ...domain.contracts import RuleValue

_rule_value_adapter: TypeAdapter[RuleValue] = TypeAdapter(bool | int | float | str)


def column_values[Value](frame: pl.DataFrame, name: str, expected: type[Value]) -> list[Value]:
    """Read one required Polars column through the shared typed boundary."""
    return series_values(frame.get_column(name), expected)


def frame_value[Value](frame: pl.DataFrame, index: int, name: str, expected: type[Value]) -> Value:
    """Read one required Polars cell through the shared typed boundary."""
    value = frame.item(index, name)
    if expected is list:
        value = value.to_list()
    return TypeAdapter(expected).validate_python(value, strict=True)


def optional_column_values[Value](
    frame: pl.DataFrame, name: str, expected: type[Value]
) -> list[Value | None]:
    """Read one nullable Polars column through the shared typed boundary."""
    adapter = TypeAdapter(expected)
    return [
        None if value is None else adapter.validate_python(value, strict=True)
        for value in frame.get_column(name).to_list()
    ]


def optional_frame_value[Value](
    frame: pl.DataFrame, index: int, name: str, expected: type[Value]
) -> Value | None:
    """Read one nullable Polars cell through the shared typed boundary."""
    value = frame.item(index, name)
    if value is None:
        return None
    if expected is list:
        value = value.to_list()
    return TypeAdapter(expected).validate_python(value, strict=True)


def series_values[Value](series: pl.Series, expected: type[Value]) -> list[Value]:
    """Read one Polars series through the shared typed boundary."""
    adapter = TypeAdapter(expected)
    return [adapter.validate_python(value, strict=True) for value in series.to_list()]


def scalar_frame_value(frame: pl.DataFrame, index: int = 0) -> RuleValue:
    """Read the one populated scalar result through the validated Polars boundary."""
    return scalar_row_value(frame.row(index, named=True))


def scalar_row_value(row: Mapping[str, JsonValue]) -> RuleValue:
    """Read the one populated scalar from a Polars row through validation."""
    for name in ("boolean_value", "integer_value", "float_value", "category_value"):
        value = row[name]
        if value is not None:
            return _rule_value_adapter.validate_python(value, strict=True)
    raise TypeError("the rule emitted no scalar value")
