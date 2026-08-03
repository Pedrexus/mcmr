from .groups import ParameterUseFields


class ParameterUse(ParameterUseFields):
    """Retain one annotated parameter and every resolved direct operation."""

    operations: list[str] = []
    attribute_reads: list[str] = []
    all_uses_known: bool = True
    is_return_value: bool = False
