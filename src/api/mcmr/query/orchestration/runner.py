import asyncio
from functools import partial
from typing import TYPE_CHECKING, cast

from anyio.to_thread import run_sync

from ...execution import ClassificationBackend
from ...execution.queries import ModelQuery, is_model_query
from ..contracts import RuleQuery
from .planning import ResolvedRule
from .query import QueryExecution

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ...checking.evaluations import PreparedRule, TableEvaluationReport
    from ...domain.contracts import RuleDependency
    from ...domain.policy import Policy
    from ...table import RepositoryTables


class TableRunner:
    """Inject lazy repository tables, resolve models, and execute one query graph."""

    def __init__(self, dependencies: Mapping[type, RuleDependency]) -> None:
        self.dependencies = dependencies

    async def report(
        self,
        tables: RepositoryTables,
        rules: Sequence[PreparedRule],
        *,
        policies: Mapping[str, Policy | None],
        fix_counts: Mapping[str, int],
        failure_limit: int | None,
    ) -> TableEvaluationReport:
        """Resolve every model query once while deterministic rules remain lazy."""
        accepted = self._accepted_paths(tables, rules)
        planned = [
            self._judged(query, policies[prepared.path])
            for prepared, query in zip(rules, self._planned(tables, rules, accepted), strict=True)
        ]
        queries = await asyncio.gather(*(self._resolve(query) for query in planned))
        resolved = self._resolved(
            rules=rules,
            queries=queries,
            accepted=accepted,
            policies=policies,
            fix_counts=fix_counts,
        )
        execution = QueryExecution(
            tables=tables,
            rules=resolved,
            failure_limit=failure_limit,
        )
        return await run_sync(partial(execution.report))

    @staticmethod
    def _accepted_paths(
        tables: RepositoryTables,
        rules: Sequence[PreparedRule],
    ) -> dict[str, list[str]]:
        family_paths = {
            family: table.frame(next(iter(table.relation_type)))
            .get_column("path")
            .unique()
            .to_list()
            for family, table in tables.items()
        }
        return {
            prepared.path: [
                path
                for path in family_paths[prepared.primary_family]
                if prepared.accepts_path(path)
            ]
            for prepared in rules
        }

    @staticmethod
    def _judged(
        query: RuleQuery | ModelQuery,
        policy: Policy | None,
    ) -> RuleQuery | ModelQuery:
        """Tell a contextual query what this project reports for each category it may answer."""
        if policy is None or not is_model_query(query):
            return query
        return query.judged(policy.reported(query.category))

    @staticmethod
    def _resolved(
        *,
        rules: Sequence[PreparedRule],
        queries: Sequence[RuleQuery],
        accepted: Mapping[str, Sequence[str]],
        policies: Mapping[str, Policy | None],
        fix_counts: Mapping[str, int],
    ) -> list[ResolvedRule]:
        return [
            ResolvedRule(
                prepared=prepared,
                policy=policies[prepared.path],
                fix_count=fix_counts[prepared.path],
                query=query,
                accepted_paths=list(accepted[prepared.path]),
            )
            for prepared, query in zip(rules, queries, strict=True)
        ]

    def _planned(
        self,
        tables: RepositoryTables,
        rules: Sequence[PreparedRule],
        accepted: Mapping[str, Sequence[str]],
    ) -> list[RuleQuery | ModelQuery]:
        return [self._query(tables, prepared, accepted[prepared.path]) for prepared in rules]

    def _query(
        self,
        tables: RepositoryTables,
        prepared: PreparedRule,
        accepted_paths: Sequence[str],
    ) -> RuleQuery | ModelQuery:
        query = prepared.rule.invoke(
            tables,
            settings=prepared.settings,
            dependencies=self.dependencies,
            languages=prepared.table_languages,
        )
        if is_model_query(query):
            return query.selected(
                accepted_paths,
                None if str(prepared.scope) == "general" else str(prepared.scope),
            )
        if isinstance(query, RuleQuery):
            return query
        raise TypeError(f"{prepared.path} returned {type(query).__name__} instead of a query")

    async def _resolve(self, query: RuleQuery | ModelQuery) -> RuleQuery:
        if isinstance(query, RuleQuery):
            return query
        backend = cast("ClassificationBackend", self.dependencies[ClassificationBackend])
        return await backend.resolve(query)
