import polars as pl
import pytest

from mcmr.query import (
    column_values,
    frame_value,
    optional_column_values,
    optional_frame_value,
    scalar_row_value,
    series_values,
)


def test_column_helpers_cross_the_typed_polars_boundary() -> None:
    frame = pl.DataFrame(
        {
            "names": ["first", "second"],
            "optional": pl.Series([1, None], dtype=pl.Int64),
            "groups": [["first", "second"], ["third"]],
        }
    )

    assert column_values(frame, "names", str) == ["first", "second"]
    assert optional_column_values(frame, "optional", int) == [1, None]
    assert series_values(frame.get_column("names"), str) == ["first", "second"]
    assert frame_value(frame, 0, "groups", list) == ["first", "second"]
    assert optional_frame_value(frame, 0, "groups", list) == ["first", "second"]
    assert optional_frame_value(frame, 0, "optional", int) == 1
    assert optional_frame_value(frame, 1, "optional", int) is None


def test_scalar_row_requires_one_populated_value() -> None:
    with pytest.raises(TypeError, match="the rule emitted no scalar value"):
        scalar_row_value(
            {
                "boolean_value": None,
                "integer_value": None,
                "float_value": None,
                "category_value": None,
            }
        )
