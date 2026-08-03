from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from ....domain.primitives import NonEmptyStr


class KernelLaunchFact(Fact):
    """Describe one kernel launch and its execution configuration."""

    kernel: str = ""
    grid: NonEmptyStr
    block: NonEmptyStr
    dynamic_shared_bytes: str = ""
    stream: str = ""
    enclosing_function: str = ""
    unit_uses_streams: bool = False
