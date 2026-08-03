from mcmr.checking.engine import RuleEngine
from mcmr.execution import ClassificationBackend, CodexBackend
from mcmr.facts import FunctionFact

from ..support import built_catalog, family_of


def test_rule_planner_builds_connected_graphs_from_declared_tables() -> None:
    catalog = built_catalog()
    engine = RuleEngine(rules=catalog.rules)

    assert len(catalog.rules) == 275
    assert len(engine.prepared) == sum(not rule.injected for rule in catalog.rules)
    assert all(rule.table_native for rule in catalog.rules)
    assert engine.families == {family for rule in catalog.rules for _, family in rule.tables}
    assert sum(len(batch.rules) for batch in engine.batches) == len(engine.prepared)
    assert all(
        left.families.isdisjoint(right.families)
        for index, left in enumerate(engine.batches)
        for right in engine.batches[index + 1 :]
    )


def test_rule_planner_compiles_settings_exclusions_and_dependency_eligibility() -> None:
    catalog = built_catalog()
    deterministic = next(
        rule for rule in catalog.rules if family_of(rule) is FunctionFact and not rule.injected
    )
    contextual = next(
        rule for rule in catalog.rules if family_of(rule) is FunctionFact and rule.injected
    )
    settings = {deterministic.callable_path: {"maximum_lines": 7}}
    exclusions = {deterministic.callable_path: ["tests/**"]}

    offline = RuleEngine(
        rules=[deterministic, contextual],
        settings=settings,
        exclusions=exclusions,
    ).prepared
    online = RuleEngine(
        rules=[deterministic, contextual],
        settings=settings,
        exclusions=exclusions,
        dependencies={ClassificationBackend: CodexBackend(binary="unused")},
    ).prepared

    prepared = offline[0]
    assert (
        [rule.path for rule in offline],
        {rule.path for rule in online},
        prepared.settings,
        prepared.accepts_path("tests/example.py"),
        prepared.accepts_path("src/example.py"),
    ) == (
        [deterministic.callable_path],
        {deterministic.callable_path, contextual.callable_path},
        settings[deterministic.callable_path],
        False,
        True,
    )


def test_rule_planner_counts_only_query_owned_fixes() -> None:
    catalog = built_catalog()
    engine = RuleEngine(rules=catalog.rules)

    assert engine.fix_counts == {
        rule.callable_path: int(rule.query_fix_safety is not None) for rule in catalog.rules
    }
    assert sum(engine.fix_counts.values()) == sum(bool(item.fixes) for item in catalog.definitions)
