from patos import FrozenModel


class Diagnostic(FrozenModel):
    """One finding an upstream tool reported, in the shape every adapter reduces its output to."""

    path: str
    line: int
    rule: str = ""
    detail: str = ""
