from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mcmr import RulePolicies
from mcmr.checking.engine import RuleEngine
from mcmr.domain.contracts import Edit, Move
from mcmr.facts import ClassFact
from mcmr.plugins import RepositoryTables
from mcmr.query.runtime import TableRunner
from mcmr.table import AnalysisSession, ClassRelation

from ...support import built_catalog

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.checking.evaluations import PreparedRule, TableEvaluationReport
    from mcmr.domain.contracts import RuleContract, RuleSetting
    from mcmr.domain.policy import Policy


def all_class_rules() -> list[RuleContract]:
    """Return every deterministic ClassFact rule in catalog order."""
    catalog = built_catalog()
    paths = {
        definition.callable
        for definition in catalog.definitions
        if definition.fact == ClassFact.__name__ and definition.lane == "deterministic"
    }
    return [rule for rule in catalog.rules if rule.callable_path in paths]


def policies(rules: Sequence[PreparedRule]) -> dict[str, Policy | None]:
    """Return the configured policy selected for every prepared class rule."""
    configured = RulePolicies()
    definitions = {definition.callable: definition for definition in built_catalog().definitions}
    return {
        rule.path: configured.policy(
            rule_id=definitions[rule.path].id,
            candidate=definitions[rule.path].policy,
        )
        for rule in rules
    }


async def report(
    session: AnalysisSession,
    engine: RuleEngine,
    failure_limit: int | None = None,
) -> TableEvaluationReport:
    """Run the complete class query graph once without a row fallback."""
    tables = RepositoryTables()
    tables.add(session.class_tables())
    return await TableRunner(engine.dependencies).report(
        tables,
        engine.prepared,
        policies=policies(engine.prepared),
        fix_counts=engine.fix_counts,
        failure_limit=failure_limit,
    )


def varied_repository(root: Path) -> Path:
    """Write class evidence for groups, methods, regions, and shared model files."""
    (root / "domain.py").write_text(
        "class MessageContent:\n    pass\n\nclass MessageKind:\n    pass\n",
        encoding="utf-8",
    )
    for name in ["api.py", "jobs.py"]:
        (root / name).write_text(
            "from domain import MessageContent, MessageKind\n",
            encoding="utf-8",
        )
    (root / "utility.py").write_text(
        """class Factory:
    @classmethod
    def build(cls):
        return cls()

    @staticmethod
    def create():
        return Factory.build()

class Regional:
    def alpha(self):
        pass

    # region second
    def zeta(self):
        pass

    def beta(self):
        pass
""",
        encoding="utf-8",
    )
    models = root / "models"
    models.mkdir()
    (models / "__init__.py").write_text("", encoding="utf-8")
    (models / "records.py").write_text(
        """from pydantic import BaseModel

class First(BaseModel):
    value: int

class Second(BaseModel):
    value: int
""",
        encoding="utf-8",
    )
    return root


@pytest.mark.anyio
async def test_complete_class_plan_executes_every_rule_once_without_rows() -> None:
    package_root = Path(__file__).parents[3]
    table, engine = (
        AnalysisSession(
            package_root / "src",
            suffixes=[".py"],
            typed_families=[ClassFact],
        ).class_tables(),
        RuleEngine(rules=all_class_rules()),
    )
    prepared, tables = engine.prepared, RepositoryTables()
    tables.add(table)
    result = await TableRunner(engine.dependencies).report(
        tables,
        prepared,
        policies=policies(prepared),
        fix_counts=engine.fix_counts,
        failure_limit=None,
    )

    assert (
        len(prepared),
        len(result.summaries),
        result.stats.rule_execution_count,
        result.stats.table_query_count,
        hasattr(result.stats, "row_call_count"),
    ) == (16, len(prepared), len(prepared), len(prepared), False)
    assert not hasattr(result.stats, "row_calls_by_family")
    assert result.stats.table_queries_by_family == {ClassFact.__name__: len(prepared)}
    assert result.stats.fact_count == table.frame(ClassRelation.FACTS).height
    assert all(
        summary.observation_count == result.stats.fact_count for summary in result.summaries
    )


@pytest.mark.anyio
async def test_class_plan_preserves_nondefault_settings_and_exclusions() -> None:
    package_root = Path(__file__).parents[3]
    selected = all_class_rules()
    by_name = {rule.qualname: rule.callable_path for rule in selected}
    settings: dict[str, dict[str, RuleSetting]] = {
        by_name["class_method_order"]: {
            "lifecycle": ["__init__"],
            "visibility_order": ["private", "internal", "protected", "public"],
            "kind_order": ["method", "class_method", "static_method", "property"],
            "alphabetical": False,
        },
        by_name["explicit_registry_name"]: {"registry_bases": {"FrozenModel"}},
        by_name["coupled_nested_type_candidate"]: {
            "suffixes": ["Fact", "Relation", "Plan", "Row", "Strategy"],
            "minimum_types": 1,
            "minimum_coimports": 1,
            "maximum_type_lines": 1_000,
            "minimum_prefix_length": 1,
        },
    }
    engine = RuleEngine(
        rules=selected,
        settings=settings,
        exclusions={rule.callable_path: ("mcmr/backends.py",) for rule in selected},
    )
    result = await report(
        AnalysisSession(
            package_root / "src",
            suffixes=[".py"],
            typed_families=[ClassFact],
        ),
        engine,
    )

    failures = list(result.failures)
    assert not hasattr(result.stats, "row_call_count")
    assert failures
    assert all(item.span.path != "mcmr/backends.py" for item in failures)


@pytest.mark.anyio
async def test_class_plan_keeps_exact_native_findings_and_order(tmp_path: Path) -> None:
    session = AnalysisSession(
        varied_repository(tmp_path),
        suffixes=[".py"],
        typed_families=[ClassFact],
    )
    result = await report(session, RuleEngine(rules=all_class_rules()))
    failures = list(result.failures)
    findings = [finding for failure in failures for finding in failure.findings]

    expected_fragments = {
        "co-imported by 2 modules",
        "static method `Factory.create`",
        "models/records.py` declares 2",
    }
    assert {
        fragment
        for fragment in expected_fragments
        if any(fragment in finding.message for finding in findings)
    } == expected_fragments
    ordered = next(finding for finding in findings if "`Regional` declares" in finding.message)
    assert isinstance(ordered.repair, Edit)
    assert isinstance(ordered.repair.plan.rewrites[0], Move)
    assert [failure.span.path for failure in failures] == sorted(
        failure.span.path for failure in failures
    )


@pytest.mark.anyio
async def test_class_plan_honors_a_global_failure_limit(tmp_path: Path) -> None:
    session = AnalysisSession(
        varied_repository(tmp_path),
        suffixes=[".py"],
        typed_families=[ClassFact],
    )
    result = await report(session, RuleEngine(rules=all_class_rules()), failure_limit=1)
    assert len(list(result.failures)) <= 1
