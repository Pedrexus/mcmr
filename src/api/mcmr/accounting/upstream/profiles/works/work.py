from .source import CitedSource


class Work(CitedSource):
    """One published work a rule may cite."""

    title: str

    @property
    def citation_title(self) -> str:
        """Return the verbatim title that identifies this work."""
        return self.title
