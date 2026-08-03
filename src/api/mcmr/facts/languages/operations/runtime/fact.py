from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .check import RuntimeTypeCheck


class RuntimeTypeCheckFact(Fact):
    """Describe runtime type checks and the protocols they require."""

    checks: list[RuntimeTypeCheck] = []
