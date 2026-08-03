from patos import FrozenModel


class UpstreamRule(FrozenModel):
    """Identify one rule of one upstream tool by its code, its symbol, or both."""

    tool: str
    code: str = ""
    symbol: str = ""
