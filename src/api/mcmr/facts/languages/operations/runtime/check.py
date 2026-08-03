from patos import FrozenModel


class RuntimeTypeCheck(FrozenModel):
    """Retain a concrete type check and its guarded operations."""

    concrete_type: str
    guarded_operations: list[str] = []
    can_use_eafp: bool = False
