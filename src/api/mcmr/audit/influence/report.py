from functools import cached_property
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import Field

from ...accounting.upstream import ClaimIndex, SourceKind, ToolRegistry, WorkRegistry
from .row import Influence

if TYPE_CHECKING:
    from collections.abc import Sequence


class InfluenceReport(FrozenModel):
    """Rank every source the catalog cites by how much of the catalog rests on it."""

    index: ClaimIndex
    works: WorkRegistry = Field(default_factory=WorkRegistry.load)
    tools: ToolRegistry = ToolRegistry()

    @cached_property
    def citations(self) -> dict[str, list[str]]:
        """Return the rule behind every reference, keyed by the source that reference names."""
        cited: dict[str, list[str]] = {}
        for definition, reference in self.index.references:
            cited.setdefault(reference.source, []).append(definition.id)
        return cited

    @cached_property
    def rows(self) -> list[Influence]:
        """Return one row per source, the most referenced first and ties broken by title."""
        rows = [self.row(source, rules) for source, rules in self.citations.items()]
        return sorted(rows, key=lambda row: (-row.references, -row.rules, row.source))

    @cached_property
    def uncited(self) -> list[str]:
        """Return every registered work no rule cites."""
        return sorted(work.title for work in self.works.works if work.title not in self.citations)

    def of(self, kind: SourceKind) -> list[Influence]:
        """Return the rows of one kind, keeping the order the whole table is sorted in."""
        return [row for row in self.rows if row.kind is kind]

    def row(self, source: str, rules: Sequence[str]) -> Influence:
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

    def tally(self) -> dict[SourceKind, int]:
        """Return how many distinct sources of each kind the catalog cites."""
        return {kind: len(self.of(kind)) for kind in SourceKind}
