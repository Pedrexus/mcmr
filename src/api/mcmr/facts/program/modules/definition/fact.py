from typing import TYPE_CHECKING, Literal

from patos import FrozenModel

from .groups import ModuleFields

if TYPE_CHECKING:
    from ....foundation import NodeRef


class ModuleFact(ModuleFields):
    """Describe one source module and its resolved members."""

    class Member(FrozenModel):
        """Describe one member a source module declares."""

        name: str
        kind: Literal["class", "function", "unknown"] = "unknown"
        source: str = ""

    is_test: bool = False
    declares_all: bool = False
    all_declarations: list[NodeRef] = []
    has_only_imports_and_all: bool = False
    members: list[Member] = []
