from patos import FrozenModel

from ....foundation import NodeRef, SourceSpan


class DataFieldRepair(FrozenModel):
    """Retain the literal a field reference named and the rewrite a catalog proof licenses."""

    node: NodeRef = NodeRef(id="", span=SourceSpan(path=""))
    replacement: str = ""
