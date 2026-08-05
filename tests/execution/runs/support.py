from typing import TYPE_CHECKING

from mcmr.domain.contracts import RuleLane, RuleScope
from mcmr.facts import FunctionFact, ModuleFact, SourceSpan
from mcmr.kernel import KernelStats
from mcmr.plugins import Fact, RepositoryTables, fact_table
from mcmr.rulebook.catalog import RuleDefinition, RuleDocumentation, RuleIdentity

from ...support import built_catalog

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mcmr import (
        Numeric,
    )
    from mcmr.domain.contracts import RuleContract
from mcmr.plugins import Table


class TableSessionProbe:
    """Return a controlled native marker stream for integration guards."""

    def __init__(
        self,
        markers: Sequence[str],
        tables: RepositoryTables | None = None,
    ) -> None:
        self.markers = markers
        self.tables = RepositoryTables() if tables is None else tables

    @staticmethod
    def kernel_stats(total_nanoseconds: int) -> KernelStats:
        """Return the bounded timing the coordinator supplies after table execution."""
        return KernelStats(total_nanoseconds=total_nanoseconds)

    def table(self, family: type[Fact]) -> Table[Fact]:
        """Return one prepared native table by its typed family."""
        return self.tables[family]

    def table_markers(self) -> Iterator[str]:
        """Yield the marker sequence under test."""
        yield from self.markers


def module_session(
    markers: Sequence[str] = (),
    table: Table[Fact] | None = None,
    languages: Sequence[str] = (),
) -> TableSessionProbe:
    """Return a probe that also delivers the per-module table every run reads languages from."""
    tables = RepositoryTables()
    tables.add(
        fact_table(
            ModuleFact,
            [
                ModuleFact(
                    key=f"module:{name}", span=SourceSpan(path=f"sample.{name}"), language=name
                )
                for name in languages
            ],
        )
    )
    if table is not None:
        tables.add(table)
    return TableSessionProbe([*markers, ModuleFact.__name__], tables)


def definition(
    identifier: str,
    *,
    output: str = "int",
    unit: str = "count",
    policy: Numeric | None = None,
    scope: RuleScope = RuleScope.GENERAL,
) -> RuleDefinition:
    """Build one compact deterministic definition for accumulator tests."""
    return RuleDefinition(
        identity=RuleIdentity(
            id=identifier,
            callable=f"mcmr.rules.{scope}.deterministic.demo.r0001.{identifier.lower()}",
            scope=scope,
            lane=RuleLane.DETERMINISTIC,
            family="demo",
            fact="ModuleFact",
        ),
        output=output,
        unit=unit,
        policy=policy,
        documentation=RuleDocumentation(summary="", definition="", examples=""),
    )


def dependency_rules() -> tuple[
    RuleContract,
    RuleDefinition,
    RuleContract,
    RuleDefinition,
]:
    """Return the external dependency rule and one native function rule it activates."""
    catalog = built_catalog()
    dependency = next(item for item in catalog.rules if item.id == "ALL-DEPE0002")
    native = next(
        item
        for item in catalog.rules
        if item.primary_family is FunctionFact
        and not item.injected
        and ".python." in item.callable_path
    )
    return dependency, catalog.definition(dependency), native, catalog.definition(native)
