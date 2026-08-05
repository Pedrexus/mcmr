from patos import FrozenModel

from ...foundation import NodeRef


class TestCallSite(FrozenModel):
    """Retain one resolved call a collected test owns."""

    qualified_name: str
    path: str
    node: NodeRef | None = None
    target_id: str = ""
    is_first_party: bool = False
