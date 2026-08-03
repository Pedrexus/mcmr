from patos import FrozenModel


class ScanConfiguration(FrozenModel):
    """Hold source discovery choices shared by every configured check."""

    suffixes: list[str] = []
