from functools import cached_property
from operator import attrgetter
from typing import TYPE_CHECKING

from patos import FrozenModel

from ....domain.contracts import RuleDefinition
from .parser import ReferenceParser

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .entry import Reference


class ClaimIndex(FrozenModel):
    """Collect every coverage claim the catalog's own docstrings state."""

    definitions: list[RuleDefinition]
    parser: ReferenceParser = ReferenceParser()

    @cached_property
    def by_identity(self) -> dict[tuple[str, str], list[Reference]]:
        """Return every claim keyed by the tool and each identity token it names."""
        index: dict[tuple[str, str], list[Reference]] = {}
        for claim in self.claims:
            upstream = claim.claimed_upstream
            for token in (upstream.code, upstream.symbol):
                if token:
                    index.setdefault((upstream.tool, token), []).append(claim)
        return index

    @cached_property
    def claims(self) -> list[Reference]:
        """Return every reference that claims coverage, in rule order."""
        return [
            reference.model_copy(
                update={
                    "rule": definition.id,
                    "summary": definition.documentation.summary,
                    "scope": definition.scope,
                    "fact": definition.fact,
                }
            )
            for definition, reference in self.references
            if reference.upstream is not None and reference.relation.coverage is not None
        ]

    @cached_property
    def references(self) -> list[tuple[RuleDefinition, Reference]]:
        """Return every reference every rule states, beside its rule."""
        return [
            (definition, reference)
            for definition in self.definitions
            for reference in self.parser.parse(definition.documentation.references)
        ]

    def of(self, *, tool: str, code: str, symbol: str) -> Sequence[Reference]:
        """Return every claim naming one tool rule through either identity token."""
        found = {
            claim.rule: claim
            for token in (code, symbol)
            if token
            for claim in self.by_identity.get((tool, token), ())
            if claim.claimed_upstream.code in {"", code}
            and claim.claimed_upstream.symbol in {"", symbol}
        }
        return sorted(found.values(), key=attrgetter("rule"))
