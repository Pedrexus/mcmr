from abc import ABC, abstractmethod
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

from patos import FrozenModel

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import CallFact, ClassFact, FunctionFact, ImportBindingFact, SyntaxFact
from mcmr.kernel import Kernel
from mcmr.plugins import Fact, Table, fact_table
from mcmr.query import RuleQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.table import AnalysisSession

from ....support import kernel_binary
from ...adapters import scalar_row
from ...contracts.report import Report
from ...contracts.site import Site

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping


@cache
def catalog() -> Catalog:
    """Return the whole rule catalog, built once for every comparison in the suite."""
    return Catalog(modules=RuleModuleDiscovery().modules)


@cache
def contract(rule_id: str) -> RuleContract:
    """Return the callable one rule identifier names through the validated catalog."""
    built = catalog()
    definition = next(item for item in built.definitions if item.id == rule_id)
    return next(item for item in built.rules if item.callable_path == definition.callable)


@cache
def extracted(root: Path, family: type[Fact], *suffixes: str) -> list[Fact]:
    """Return one fact family the real kernel builds over one tree."""
    workspace = Kernel(binary=kernel_binary(), root=root, suffixes=suffixes).build(
        [family.__name__], {family.__name__: family}
    )
    return workspace.streams.get(family, [])


@cache
def tabled(root: Path, family: type[Fact], *suffixes: str) -> Table[Fact]:
    """Return one native table family built once over the whole repository."""
    session = AnalysisSession(root, suffixes=suffixes, typed_families=(family,))
    specialized: dict[type[Fact], Callable[[], Table[Fact]]] = {
        CallFact: lambda: cast("Table[Fact]", session.call_tables()),
        ClassFact: lambda: cast("Table[Fact]", session.class_tables()),
        FunctionFact: lambda: cast("Table[Fact]", session.function_tables()),
        ImportBindingFact: lambda: cast("Table[Fact]", session.import_binding_tables()),
        SyntaxFact: lambda: cast("Table[Fact]", session.syntax_tables()),
    }
    factory = specialized.get(family)
    return session.table(family) if factory is None else factory()


def retained_fact(subject: Fact) -> Table[Fact]:
    """Normalize one generic fact through the in-memory native table boundary."""
    return fact_table(type(subject), [subject])


class RuleReader(FrozenModel, ABC):
    """Run one MCMR rule over one tree through the real kernel and say where it answered.

    A rule locates a finding as precisely as the fact it read allows, and that is a property of the
    rule rather than of the comparison, so each subclass is one of the three answers a rule can
    give. Nothing here reads a rule's condition a second time: the rule is always the judge and a
    reader only asks it and records where it spoke.
    """

    rule_id: str
    family: type[Fact]
    settings: dict[str, RuleSetting] = {}
    languages: list[str] = []
    suffixes: list[str] = []

    @property
    def name(self) -> str:
        """Return the rule this reader runs."""
        return self.rule_id

    def counted(self, subject: Fact) -> int:
        """Return how many findings the rule answered with about one fact."""
        value = scalar(self.queried(subject))
        return int(value) if isinstance(value, bool | int) else 0

    def facts(self, root: Path) -> list[Fact]:
        """Return the family this rule reads, narrowed to the languages the case asked for."""
        stream = extracted(root, self.family, *self.suffixes)
        if not self.languages:
            return stream
        return [fact for fact in stream if fact.language in self.languages]

    def narrowed_values(self, query: RuleQuery) -> list[Mapping[str, RuleValue | None]]:
        """Narrow one completed query's values to requested languages."""
        rows = query.values.collect().iter_rows(named=True)
        return [row for row in rows if not self.languages or row["language"] in self.languages]

    def queried(self, subject: Fact) -> RuleQuery:
        """Return the deterministic table query planned for one retained fact."""
        table = retained_fact(subject)
        result = contract(self.rule_id).invoke_table(
            table, settings=self.settings, dependencies={}
        )
        if not isinstance(result, RuleQuery):
            raise TypeError(f"{self.rule_id} returned a contextual model query")
        return result

    def query(self, root: Path) -> RuleQuery:
        """Run this rule once over the native table for the whole repository."""
        result = contract(self.rule_id).invoke_table(
            tabled(root, self.family, *self.suffixes),
            settings=self.settings,
            dependencies={},
        )
        if not isinstance(result, RuleQuery):
            raise TypeError(f"{self.rule_id} returned a contextual model query")
        return result

    def report(self, root: Path) -> Report:
        """Return where this rule reported over one tree."""
        return Report(reader=self.name, sites=list(self.sites(root)))

    @abstractmethod
    def sites(self, root: Path) -> Iterable[Site]:
        """Return every site this rule reported over one tree."""

    def stated(self, subject: Fact) -> list[Site]:
        """Return the span of every finding the rule stated about one fact."""
        query = self.queried(subject)
        if query.findings is None:
            return []
        return [
            Site(path=row["path"], line=row["start_line"], through=row["end_line"])
            for row in query.findings.rows.collect().iter_rows(named=True)
        ]

    def values(self, root: Path) -> list[Mapping[str, RuleValue | None]]:
        """Return this rule's value rows narrowed to requested languages."""
        return self.narrowed_values(self.query(root))


def scalar[Value: RuleValue](query: RuleQuery[Value]) -> Value:
    """Return the scalar from a query that produced exactly one value row."""
    values = query.values.collect()
    if values.height != 1:
        raise ValueError(f"expected one value row and received {values.height}")
    return cast("Value", scalar_row(values.row(0, named=True)))
