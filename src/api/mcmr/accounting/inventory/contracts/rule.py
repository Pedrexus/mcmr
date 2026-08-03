from patos import FrozenModel


class ToolRule(FrozenModel):
    """Identify one rule in the frozen inventory of one upstream tool."""

    code: str = ""
    symbol: str
    group: str = ""
