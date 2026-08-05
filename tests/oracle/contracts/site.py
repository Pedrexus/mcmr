from patos import FrozenModel


class Site(FrozenModel):
    """One located finding, as a path relative to the tree and the lines it covers.

    The path is relative to the tree rather than a base name, because a real checkout holds a dozen
    files called `__init__.py` and a one-file fixture folds every reader onto one name whatever
    either of them answered. A point finding covers one line and a rule reading a whole declaration
    covers its range, which is what lets two readers pinned at different granularities be compared
    without either being widened to meet the other.
    """

    path: str
    line: int
    through: int

    @property
    def width(self) -> int:
        """Return how many lines this site covers."""
        return self.through - self.line + 1

    @classmethod
    def at(cls, path: str, line: int) -> Site:
        """Return the site one reader named by a single line."""
        return cls(path=path, line=line, through=line)

    def holds(self, other: Site) -> bool:
        """Whether this site covers the whole of another one in the same file."""
        return (
            self.path == other.path and self.line <= other.line and other.through <= self.through
        )
