from patos import FrozenModel


class RuleDocumentation(FrozenModel):
    """Retain the complete reStructuredText documentation of one rule."""

    summary: str
    definition: str
    evidence: str = ""
    exceptions: str = ""
    examples: str
    references: list[str] = []
