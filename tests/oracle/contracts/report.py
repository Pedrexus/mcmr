from collections import Counter
from operator import attrgetter
from typing import TYPE_CHECKING

from patos import FrozenModel

if TYPE_CHECKING:
    from collections.abc import Sequence

from .site import Site


class Report(FrozenModel):
    """Every finding one reader stated over one tree, as a multiset of located sites.

    A multiset rather than a set, because two findings on one line are two findings and a reader
    that states one of them has not agreed. Nothing here exposes a total, so a comparison cannot be
    written against a count, which is the weak form this whole harness exists to make hard.
    """

    reader: str
    sites: list[Site] = []

    @property
    def tally(self) -> Counter[Site]:
        """Return how many findings this reader stated at each site."""
        return Counter(self.sites)

    def folded(self, ranges: Sequence[Site], site: Site) -> Site:
        """Return the narrowest range holding one point, or the site itself when none does."""
        if site.width > 1:
            return site
        return next((held for held in ranges if held.holds(site)), site)

    def minus(self, *sites: Site) -> Report:
        """Return this report without findings the other reader is documented not to state."""
        remaining = self.tally - Counter(sites)
        if sum(remaining.values()) + len(sites) != len(self.sites):
            missing = sorted(
                set(sites) - set(self.sites), key=attrgetter("path", "line", "through")
            )
            raise ValueError(f"{self.reader} never stated {missing}")
        return Report(reader=self.reader, sites=list(remaining.elements()))

    def narrowed_to(self, other: Report) -> Report:
        """Return these sites folded onto the ranges another reader states around them.

        Each reader pins a finding as precisely as its evidence allows, so Pylint names a line
        where a rule reading one declaration answers for the whole of it. Folding the finer side
        into the coarser one's ranges is what makes the two comparable, and the narrowest range
        wins so a finding in the wrong callable stays in the wrong callable rather than being
        absorbed by the class around it. A site no range holds is left where it is, so a
        disagreement stays visible instead of being swallowed.
        """
        ranges = sorted(
            {site for site in other.sites if site.width > 1}, key=lambda site: site.width
        )
        return Report(reader=self.reader, sites=[self.folded(ranges, site) for site in self.sites])

    def plus(self, *sites: Site) -> Report:
        """Return this report widened by findings the other reader is documented to state too.

        A divergence written out in full stays an equality, which is a great deal stronger than
        replacing it with a containment that any silent reader satisfies.
        """
        return Report(reader=self.reader, sites=[*self.sites, *sites])

    def states(self, *sites: Site) -> bool:
        """Whether this reader stated exactly these findings and no others.

        This is how a fixture pins what an oracle answers about it, so a comparison that passed
        because both readers went quiet fails here first.
        """
        return self.tally == Counter(sites)
