import ast
from pathlib import Path

import pytest

from mcmr.domain.contracts import RuleLane, fact_type
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery

_PACKAGE = Path(__file__).parents[2]
_rule_root = _PACKAGE / "src" / "rules" / "mcmr" / "rules"
_rule_paths = list(_rule_root.rglob("r[0-9][0-9][0-9][0-9].py"))
_rule_returns = [
    (path, node.value)
    for path in _rule_paths
    for node in ast.walk(ast.parse(path.read_text()))
    if isinstance(node, ast.Return) and node.value is not None
]


def test_builtin_catalog_preserves_every_migrated_rule() -> None:
    expected = set((_PACKAGE / "tests" / "catalog_ids.txt").read_text().splitlines())
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    definitions = catalog.definitions
    assert {definition.id for definition in definitions} == expected
    assert len(definitions) == 275
    assert all(definition.policy is not None for definition in definitions)
    assert all(definition.documentation.definition for definition in definitions)
    assert all(definition.documentation.examples for definition in definitions)
    assert all(definition.documentation.references for definition in definitions)
    assert sum(len(definition.fixes) for definition in definitions) == 31


def test_every_builtin_contract_is_one_table_query() -> None:
    """Every selected rule is planned once over its complete family relation."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    contextual = {
        definition.callable
        for definition in catalog.definitions
        if definition.lane != str(RuleLane.DETERMINISTIC)
    }

    assert all(rule.table_native for rule in catalog.rules)
    assert all(not callable(rule) for rule in catalog.rules)
    assert {rule.callable_path for rule in catalog.rules if rule.model_native} == contextual
    assert len(contextual) == 45


def test_retired_rule_ids_stay_reserved_with_a_reason() -> None:
    active = set((_PACKAGE / "tests" / "catalog_ids.txt").read_text().splitlines())

    assert set(Catalog.retirements) == {
        "ALL-ARCH0004",
        "ALL-CLAS0002",
        "ALL-DATA0005",
        "ALL-DEPE1001",
        "ALL-DEPE1002",
        "ALL-DEPE1003",
        "ALL-DEPE1004",
        "ALL-DEPE1005",
        "ALL-DOCU1001",
        "ALL-ERRO1001",
        "ALL-ERRO1002",
        "ALL-ERRO1003",
        "ALL-MIGR1001",
        "ALL-MIGR1002",
        "ALL-MIGR1003",
        "ALL-MIGR1004",
        "ALL-OBSE0001",
        "ALL-OPER1001",
        "ALL-OPER1002",
        "ALL-OPER1003",
        "ALL-OPER1004",
        "ALL-RELE1001",
        "ALL-RELI1001",
        "ALL-RELI1002",
        "ALL-RELI1004",
        "ALL-RELI1005",
        "ALL-RELI1006",
        "ALL-SECU0001",
        "ALL-SECU1001",
        "ALL-TEST0001",
        "ALL-WRIT0002",
        "ALL-WRIT0006",
        "PY-MODE0002",
        "PY-TYPE0006",
    }
    assert active.isdisjoint(Catalog.retirements)
    assert all(reason.strip() for reason in Catalog.retirements.values())


def test_fact_contracts_never_store_the_rule_answer() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    for rule in catalog.rules:
        first = next(iter(rule.signature.parameters.values()))
        required = fact_type(rule.hints[first.name])
        assert rule.qualname.rsplit(".", 1)[-1] not in required.model_fields


@pytest.mark.parametrize(
    ("path", "answer"),
    _rule_returns,
    ids=[f"{path.relative_to(_rule_root)}:{answer.lineno}" for path, answer in _rule_returns],
)
def test_no_rule_only_forwards_a_provider_verdict(path: Path, answer: ast.expr) -> None:
    """Reject a rule whose whole body reads back a decision a provider already made.

    A body such as ``sum(call.has_round_trip for call in subject.calls)`` computes nothing: the
    finding was made inside the provider and one Boolean field carries the verdict across. A rule
    has to reach its own answer from primitive evidence. Returning a measured quantity such as
    `implementation_lines` stays legitimate, because reporting a measurement is what those rules
    exist to do, so only a forwarded Boolean counts as a contract failure here.
    """
    verdict_prefixes = ("is_", "has_", "can_", "should_", "proves_", "only_", "all_", "wraps_")
    if (
        isinstance(answer, ast.Call)
        and isinstance(answer.func, ast.Name)
        and answer.func.id in {"sum", "any", "all"}
        and isinstance(answer.args[0], ast.GeneratorExp)
    ):
        answer = answer.args[0].elt
    if isinstance(answer, ast.UnaryOp) and isinstance(answer.op, ast.Not):
        answer = answer.operand

    assert not (isinstance(answer, ast.Attribute) and answer.attr.startswith(verdict_prefixes)), (
        str(path.relative_to(_rule_root))
    )


def test_provider_answer_shortcut_does_not_exist() -> None:
    """Reject a call that asks a provider for the answer instead of computing one.

    This reads the syntax rather than the characters, because the four characters also spell a
    Node import inside a script this package embeds, and a guard that a source file can trip by
    quoting another language is a guard nobody trusts twice.
    """
    package = _PACKAGE / "src"
    shortcuts = [
        str(path.relative_to(package))
        for path in package.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "require")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "require")
        )
    ]
    assert not shortcuts


_rule_functions = [
    (path, node)
    for path in _rule_paths
    for node in ast.parse(path.read_text()).body
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    and any(
        isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "rule"
        for item in node.decorator_list
    )
]


@pytest.mark.parametrize(
    ("path", "function"),
    _rule_functions,
    ids=[str(path.relative_to(_rule_root)) for path, _ in _rule_functions],
)
def test_every_rule_parameter_contributes_to_its_implementation(
    path: Path,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> None:
    parameters = {
        argument.arg
        for argument in [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ]
    }
    loaded = {
        item.id
        for statement in function.body
        for item in ast.walk(statement)
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Load)
    }

    assert not parameters - loaded, str(path.relative_to(_rule_root))


def test_rule_returns_do_not_coerce_predicates_into_counts() -> None:
    rule_root = _rule_root
    direct_integer_coercions = [
        str(path.relative_to(rule_root))
        for path in rule_root.rglob("r[0-9][0-9][0-9][0-9].py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "int"
    ]
    assert not direct_integer_coercions
