from ...accounting.upstream import CitedSource


class Influence(CitedSource):
    """Measure how much one source shaped the catalog."""

    source: str
    references: int
    rules: int

    @property
    def citation_title(self) -> str:
        """Return the source name that identifies this influence row."""
        return self.source
