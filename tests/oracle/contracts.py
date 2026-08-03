from collections import Counter
from enum import StrEnum, auto
from functools import cache
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from patos import FrozenModel

from mcmr.domain.contracts import RuleContract
from mcmr.facts import CallFact, ClassFact, Fact, FunctionFact, ImportBindingFact, SyntaxFact
from mcmr.kernel import Kernel
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.table import AnalysisSession, Table, fact_table

from ..support import kernel_binary

if TYPE_CHECKING:
    from collections.abc import Sequence


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


class Relation(StrEnum):
    """Say how what MCMR reported stands to what an upstream tool reported.

    MCMR is deliberately wider than an oracle in some places and narrower in others, and stating
    which is what keeps a difference visible instead of tuned away. An equality compares the two
    multisets, so a reader that found the same place twice as often has not agreed. A containment
    compares the distinct places instead, since a rule pinned to a declaration states one finding
    where a line-pinned reader states several and multiplicity is not a claim either can make about
    the other. A disjoint pair demands that both readers actually spoke, so it can never pass
    because one of them was silent. A union is where one MCMR rule answers what several upstream
    rules answer between them, and each of those is named rather than merged behind one selection.
    """

    EQUALS = auto()
    SUBSET = auto()
    SUPERSET = auto()
    DISJOINT = auto()
    UNION = auto()

    def stated_between(self, tools: int) -> bool:
        """Whether this relation can be stated between MCMR and that many upstream rules."""
        return tools >= 2 if self is Relation.UNION else tools == 1


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


class Reader(Protocol):
    """State where one analysis found something over one tree.

    Both halves of a comparison satisfy this, which is what lets one relation be asserted between
    an MCMR rule and an upstream tool without either side learning what the other is.
    """

    @property
    def name(self) -> str:
        """Return what this reader is called in a failure message."""
        ...

    def report(self, root: Path) -> Report:
        """Return every finding this reader states over one tree."""
        ...


class Diagnostic(FrozenModel):
    """One finding an upstream tool reported, in the shape every adapter reduces its output to."""

    path: str
    line: int
    rule: str = ""
    detail: str = ""


@cache
def catalog() -> Catalog:
    """Return the whole rule catalog, built once for every comparison in the suite.

    Discovery and validation cost about as much as one kernel run and every oracle case needs one
    rule out of the same catalog, so building it once is the difference between a suite that spawns
    subprocesses and one that also rebuilds the catalog beside every one of them.
    """
    return Catalog(modules=RuleModuleDiscovery().modules)


@cache
def contract(rule_id: str) -> RuleContract:
    """Return the callable one rule identifier names, through the catalog that validates it."""
    built = catalog()
    definition = next(item for item in built.definitions if item.id == rule_id)
    return next(item for item in built.rules if item.callable_path == definition.callable)


@cache
def extracted(root: Path, family: type[Fact], *suffixes: str) -> list[Fact]:
    """Return one fact family the real kernel builds over one tree.

    Cached by the tree it read, since several comparisons ask the same family of the same generated
    project and a kernel run is a process spawn. A tree written to after it has been read once
    would answer from the first reading, so every fixture here writes its whole tree before anyone
    asks anything about it.
    """
    workspace = Kernel(binary=kernel_binary(), root=root, suffixes=suffixes).build(
        [family.__name__], {family.__name__: family}
    )
    return workspace.streams.get(family, [])


@cache
def tabled(root: Path, family: type[Fact], *suffixes: str) -> Table[Fact]:
    """Return one native table family built once over the whole repository."""
    session = AnalysisSession(root, suffixes=suffixes, typed_families=(family.__name__,))
    if family is CallFact:
        return cast("Table[Fact]", session.call_tables())
    if family is ClassFact:
        return cast("Table[Fact]", session.class_tables())
    if family is FunctionFact:
        return cast("Table[Fact]", session.function_tables())
    if family is ImportBindingFact:
        return cast("Table[Fact]", session.import_binding_tables())
    if family is SyntaxFact:
        return cast("Table[Fact]", session.syntax_tables())
    return session.table(family)


def retained_fact(subject: Fact) -> Table[Fact]:
    """Normalize one generic fact through the in-memory native table boundary."""
    return fact_table(type(subject), [subject])
