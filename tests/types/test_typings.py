from patos import FrozenModel
from pydantic import TypeAdapter


class FrozenCollection(FrozenModel):
    """Exercise the shared sequence contract through a real Pydantic field."""

    values: list[str]


def test_model_list_accepts_general_inputs_and_round_trips_stably() -> None:
    """Lists and tuples share one ordinary validated list representation."""
    from_list = FrozenCollection(values=["one", "two"])
    from_tuple = TypeAdapter(FrozenCollection).validate_python({"values": ("one", "two")})

    assert from_list == from_tuple
    assert from_list.values == ["one", "two"]
    assert FrozenCollection.model_validate_json(from_list.model_dump_json()) == from_list
