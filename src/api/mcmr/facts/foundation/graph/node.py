from patos import FrozenModel

from ..span import SourceSpan


class NodeRef(FrozenModel):
    """Address one resolved syntax node and retain the exact source it spans.

    A fix names edited nodes through these handles, so a language backend renders the rewrite from
    a typed request instead of accepting a byte range computed inside a rule.
    """

    id: str
    span: SourceSpan
    kind: str = ""
    text: str = ""
