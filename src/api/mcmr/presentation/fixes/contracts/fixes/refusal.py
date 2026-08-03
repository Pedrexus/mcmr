from patos import FrozenModel


class FixRefusal(FrozenModel):
    """Explain why one offered edit was not rendered or retained."""

    rule: str
    summary: str
    reason: str
