from patos import FrozenModel
from pydantic import NonNegativeInt


class EnumScope(FrozenModel):
    """Retain enum reuse inside one narrow common package."""

    destination: str
    enum_count: NonNegativeInt
    reused_enum_count: NonNegativeInt
    cross_module_import_count: NonNegativeInt
