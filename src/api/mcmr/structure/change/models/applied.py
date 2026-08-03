from patos import FrozenModel

from .proposed import ProposedImport


class AppliedChange(FrozenModel):
    """Classify every proposed import after resolving it against the graph."""

    added: list[ProposedImport] = []
    removed: list[ProposedImport] = []
    unchanged: list[ProposedImport] = []
    cancelled: list[ProposedImport] = []
    unknown: list[str] = []
