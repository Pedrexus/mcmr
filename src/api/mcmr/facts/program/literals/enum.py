from patos import FrozenModel


class EnumMetadataMap(FrozenModel):
    """Retain one literal mapping keyed entirely by members of one local enum."""

    enum_name: str
    keys: list[str] = []
    values: list[str] = []
    all_keys_resolve_to_enum: bool = False
