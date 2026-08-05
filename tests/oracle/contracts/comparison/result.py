from collections import Counter
from operator import attrgetter
from typing import TYPE_CHECKING

from patos import FrozenModel

from ..report import Report
from .relation import Relation

if TYPE_CHECKING:
    from ..site import Site


class Comparison(FrozenModel):
    """One stated relation between what MCMR reported and what its oracles reported.

    The reason travels with the relation, because a difference nobody wrote down is a difference
    somebody will later delete. Every comparison carries one, and a comparison whose two sides
    disagree prints both halves rather than a Boolean.
    """

    ours: Report
    theirs: list[Report]
    relation: Relation
    reason: str

    @property
    def upstream(self) -> Report:
        """Return what the oracle side states, counting a finding two rules share only once."""
        merged: Counter[Site] = Counter()
        for report in self.theirs:
            merged |= report.tally
        return Report(
            reader=" and ".join(report.reader for report in self.theirs),
            sites=list(merged.elements()),
        )

    def aligned(self) -> tuple[Counter[Site], Counter[Site]]:
        """Return both sides expressed in each other's ranges, ready to be compared."""
        theirs = self.upstream
        return self.ours.narrowed_to(theirs).tally, theirs.narrowed_to(self.ours).tally

    def explain(self) -> str:
        """Return the whole disagreement, both readers named and every unshared site on each."""
        ours, theirs = self.aligned()
        return "\n".join(
            [
                f"{self.ours.reader} {self.relation} {self.upstream.reader} fails: {self.reason}",
                f"  only {self.ours.reader}: "
                f"{sorted((ours - theirs).elements(), key=attrgetter('path', 'line', 'through'))}",
                f"  only {self.upstream.reader}: "
                f"{sorted((theirs - ours).elements(), key=attrgetter('path', 'line', 'through'))}",
            ]
        )

    def holds(self) -> bool:
        """Whether the stated relation is what the two readers actually said."""
        ours, theirs = self.aligned()
        match self.relation:
            case Relation.EQUALS | Relation.UNION:
                return ours == theirs
            case Relation.SUBSET:
                return set(ours) <= set(theirs)
            case Relation.SUPERSET:
                return set(ours) >= set(theirs)
            case _:
                return bool(ours) and bool(theirs) and not set(ours) & set(theirs)


def differ(ours: Report, relation: Relation, *theirs: Report, because: str) -> None:
    """Assert one stated relation between an MCMR rule and the oracles it is compared against.

    `because` is required, so an equality can never be written without saying why it is one and a
    containment can never be written without saying which side is deliberately the wider reader.
    """
    if not relation.stated_between(len(theirs)):
        raise ValueError(f"{relation} cannot be stated between MCMR and {len(theirs)} tools")
    comparison = Comparison(ours=ours, theirs=theirs, relation=relation, reason=because)
    assert comparison.holds(), comparison.explain()
