from functools import cached_property

from pydantic import Field

from .bases import FrozenFlexModel
from .upstream import ClaimIndex, SourceKind, ToolRegistry, WorkRegistry


class Influence(FrozenFlexModel):
    """How much one source shaped the catalog, as references made and as rules that made them.

    The two numbers answer different questions. References counts how often the catalog leaned on
    a source and rules counts how much of the catalog leans on it at all, so a book one rule cites
    eight times and a book eight rules cite once are told apart rather than averaged into one
    figure that flatters the first.
    """

    source: str
    kind: SourceKind
    references: int
    rules: int
    author: str = ""
    link: str = ""

    @property
    def citation(self) -> str:
        """Return this source as a page cites it, the title first and the author behind it."""
        return f"{self.source}, {self.author}" if self.author else self.source


class InfluenceReport(FrozenFlexModel):
    """Rank every source the catalog cites by how much of the catalog rests on it.

    This is derived rather than maintained. Every reference already names one registered work or
    one registered tool exactly, so the table is a count of what the rules say about themselves and
    no list beside the catalog can disagree with it.
    """

    index: ClaimIndex
    works: WorkRegistry = Field(default_factory=WorkRegistry.load)
    tools: ToolRegistry = ToolRegistry()

    @cached_property
    def citations(self) -> dict[str, tuple[str, ...]]:
        """Return the rule behind every reference, keyed by the source that reference names."""
        cited: dict[str, list[str]] = {}
        for definition, reference in self.index.references:
            cited.setdefault(reference.source, []).append(definition.id)
        return {source: tuple(rules) for source, rules in cited.items()}

    @cached_property
    def rows(self) -> tuple[Influence, ...]:
        """Return one row per source, the most referenced first and ties broken by title."""
        rows = (self.row(source, rules) for source, rules in self.citations.items())
        return tuple(sorted(rows, key=lambda row: (-row.references, -row.rules, row.source)))

    @cached_property
    def uncited(self) -> tuple[str, ...]:
        """Return every registered work no rule cites, which is a row that would state nothing."""
        return tuple(
            sorted(work.title for work in self.works.works if work.title not in self.citations)
        )

    def row(self, source: str, rules: tuple[str, ...]) -> Influence:
        """Return one source's row, reading its display data from whichever registry names it."""
        made, holding = len(rules), len(set(rules))
        work = self.works.of(source)
        if work is not None:
            return Influence(
                source=work.title,
                kind=work.kind,
                references=made,
                rules=holding,
                author=work.author,
                link=work.link,
            )
        profile = self.tools.of(source)
        if profile is None:
            raise ValueError(f"{source} is neither a registered work nor a registered tool")
        return Influence(source=profile.name, kind=SourceKind.TOOL, references=made, rules=holding)

    def of(self, kind: SourceKind) -> tuple[Influence, ...]:
        """Return the rows of one kind, keeping the order the whole table is sorted in."""
        return tuple(row for row in self.rows if row.kind is kind)

    def tally(self) -> dict[SourceKind, int]:
        """Return how many distinct sources of each kind the catalog cites."""
        return {kind: len(self.of(kind)) for kind in SourceKind}
