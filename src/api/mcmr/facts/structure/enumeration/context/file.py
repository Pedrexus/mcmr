from patos import FrozenModel
from pydantic import NonNegativeInt


class EnumFile(FrozenModel):
    """Retain the shape and reuse of one file under an enums directory."""

    path: str
    top_level_class_count: NonNegativeInt
    enum_class_count: NonNegativeInt
    is_package_initializer: bool = False
    is_shared_across_unrelated_branches: bool = False
