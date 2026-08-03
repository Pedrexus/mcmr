from patos import FrozenModel

from .....domain.contracts import RuleScope


class ToolProfile(FrozenModel):
    """Describe how one upstream tool identifies and documents its rules."""

    name: str
    codes: str = ""
    documentation: str = ""
    categories: dict[str, str] = {}
    inventoried: bool = False
    languages: list[RuleScope] = []

    @property
    def slug(self) -> str:
        """Return the name this tool's frozen data files are stored under."""
        return self.name.casefold()

    def link(self, *, code: str, symbol: str) -> str:
        """Return the page documenting one rule, empty when none is derivable."""
        if not self.documentation:
            return ""
        return self.documentation.format(
            code=code,
            symbol=symbol,
            category=self.categories.get(code[:1], ""),
            path=symbol.replace("-", "/", 1),
        )
