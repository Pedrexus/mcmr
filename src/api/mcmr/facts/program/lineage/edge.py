from patos import FrozenModel


class LineageEdge(FrozenModel):
    """Retain one directed lineage edge and exact endpoint resolution."""

    source: str
    target: str
    source_exists: bool
    target_exists: bool
