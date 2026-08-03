from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from patos import FrozenModel
from pydantic import NonNegativeInt

from .....domain.policy import RulePolicies
from .....execution import ClassificationBackend
from .....project import MCMRConfiguration
from .....query.orchestration import TableExecution
from .....rulebook.catalog import Catalog
from .....rulebook.discovery import RuleModuleDiscovery
from ....engine import RuleEngine
from ...results import JudgmentAccumulator

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .....domain.contracts import RuleContract, RuleDefinition, RuleDependency
    from .....facts import Fact
    from ....evaluations import PreparedRule
    from ...results import Verdicts


class Judgment(FrozenModel):
    """Run the catalog over a repository once and judge every selected rule."""

    binary: Path
    root: Path
    policies: RulePolicies = RulePolicies()
    select: str = ""
    suffixes: list[str] = []
    failure_limit: NonNegativeInt | None = None
    configuration: MCMRConfiguration = MCMRConfiguration()

    def dependencies(self) -> dict[type, RuleDependency]:
        """Return the explicitly enabled services contextual rules may receive."""
        configured = self.configuration.contextual
        if not self.configuration.execution.contextual:
            return {}
        backend = ClassificationBackend.find(str(configured.backend))
        return {ClassificationBackend: backend.model_validate(configured, from_attributes=True)}

    def run(self) -> Verdicts:
        """Run one judgment from synchronous code through a private event loop."""
        return anyio.run(self.run_async)

    async def run_async(self) -> Verdicts:
        """Consume each connected fact graph once and retain bounded failures."""
        engine, definitions = self._engine()
        accumulator = self._accumulator(definitions)
        kernel, runnable, reads = await self._execution(engine, accumulator).run(
            self.table_families(engine.prepared),
            batches=engine.batches,
            fix_counts=engine.fix_counts,
        )
        return accumulator.finish(
            kernel,
            runnable=runnable,
            provider_read_count=reads,
            fix_count=sum(bool(definition.fixes) for definition in definitions.values()),
        )

    def table_families(self, prepared: Sequence[PreparedRule]) -> set[type[Fact]]:
        """Return the union of table annotations on every runnable rule."""
        return {family for rule in prepared for family in rule.families}

    def _accumulator(
        self,
        definitions: Mapping[str, RuleDefinition],
    ) -> JudgmentAccumulator:
        """Create the bounded mutable state for one run."""
        return JudgmentAccumulator(self.policies, list(definitions.values()), self.failure_limit)

    def _engine(self) -> tuple[RuleEngine, dict[str, RuleDefinition]]:
        """Resolve selected rule contracts and invariant execution inputs."""
        catalog = Catalog(modules=RuleModuleDiscovery().modules)
        available = catalog.definitions
        rules = self.configuration.selected(
            available,
            rules=catalog.rules,
            override=self.select,
        )
        matched = self.configuration.matched(available, self.select)
        definitions = {definition.callable: definition for definition in matched}
        return self._rule_engine(catalog, rules), definitions

    def _execution(
        self,
        engine: RuleEngine,
        accumulator: JudgmentAccumulator,
    ) -> TableExecution:
        """Bind one engine to its request-local table execution."""
        return TableExecution(
            root=self.root,
            suffixes=self.suffixes,
            dependencies=engine.dependencies,
            accumulator=accumulator,
            provider_settings=self.configuration.providers,
        )

    def _rule_engine(
        self,
        catalog: Catalog,
        rules: Sequence[RuleContract],
    ) -> RuleEngine:
        """Bind selected rules to validated settings and dependencies."""
        return RuleEngine(
            rules=list(rules),
            settings=self.configuration.settings(catalog.definitions, rules=catalog.rules),
            exclusions=self.configuration.exclusions(catalog.definitions),
            dependencies=self.dependencies(),
        )
