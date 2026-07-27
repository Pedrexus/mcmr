import ast
from enum import StrEnum
from pathlib import Path

import pytest

from mcmr.backends import ClassificationBackend
from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.engine import MockBackend, RuleEngine
from mcmr.facts import Fact, SourceSpan
from mcmr.models import RuleScope, fact_type


class FirstCategoryBackend(ClassificationBackend):
    """Return the first allowed category for full-catalog execution coverage."""

    async def classify[Category: StrEnum](
        self,
        subject: Fact,
        *,
        category: type[Category],
        instructions: str,
    ) -> Category:
        """Validate the prompt surface and choose its first closed category."""
        if not instructions:
            raise ValueError("Classification instructions cannot be empty")
        return next(iter(category))


def test_builtin_catalog_preserves_every_migrated_rule() -> None:
    expected = set(Path(__file__).with_name("catalog_ids.txt").read_text().splitlines())
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    definitions = catalog.definitions
    assert {definition.id for definition in definitions} == expected
    assert len(definitions) == 277
    assert all(definition.documentation.definition for definition in definitions)
    assert all(definition.documentation.examples for definition in definitions)
    assert all(definition.documentation.references for definition in definitions)
    assert sum(len(definition.fixes) for definition in definitions) == 23


@pytest.mark.anyio
async def test_every_builtin_contract_is_invocable_with_minimal_provider_facts() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    backend = MockBackend()
    measurements: dict[type[Fact], dict[str, bool | int | float | str]] = {}
    fact_types_by_rule: dict[str, type[Fact]] = {}
    for rule in catalog.rules:
        first = next(iter(rule.signature.parameters.values()))
        required = fact_type(rule.hints[first.name])
        fact_types_by_rule[rule.callable_path] = required
        measurements.setdefault(required, {})[
            rule.qualname.rsplit(".", 1)[-1]
        ] = await backend.evaluate(rule, required.model_construct())
    languages = sorted({scope for scope in RuleScope if scope is not RuleScope.GENERAL})
    workspace: dict[type[Fact], list[Fact]] = {}
    for required, values in measurements.items():
        available = required.model_fields
        base = {
            "span": SourceSpan(path="synthetic.py"),
            "name": "synthetic",
            "module": "synthetic",
            "mechanism": "binary",
            "declared_language": "python",
            "kind": "class",
            "qualname": "synthetic",
        } | {name: value for name, value in values.items() if name in available}
        workspace[required] = [
            required.model_validate(
                {
                    name: value
                    for name, value in (
                        base | {"key": f"{required.__name__}:{language}", "language": language}
                    ).items()
                    if name in available
                }
            )
            for language in languages
        ]
    report = await RuleEngine(
        rules=catalog.rules,
        fixes=catalog.fixes,
        dependencies={ClassificationBackend: FirstCategoryBackend()},
    ).run(workspace)
    plans = [
        fix.invoke(workspace[fact_types_by_rule[fix.rule_callable]][0], {})
        for fix in catalog.fixes
    ]
    expected = sum(
        len(languages) if definition.scope is RuleScope.GENERAL else 1
        for definition in catalog.definitions
    )
    assert report.stats.invocation_count == expected
    assert report.stats.skipped_rule_count == 0
    assert all(plan is None for plan in plans)


def test_every_deterministic_rule_has_a_direct_semantic_assertion() -> None:
    rule_root = Path(__file__).parents[1] / "src" / "mcmr" / "rules"
    deterministic = {
        ".".join(path.with_suffix("").parts[-6:])
        for path in rule_root.rglob("r[0-9][0-9][0-9][0-9].py")
        if "deterministic" in path.parts
    }
    asserted: set[str] = set()
    for path in Path(__file__).parent.glob("test_*.py"):
        tree = ast.parse(path.read_text())
        imports = {
            alias.asname or alias.name: node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and ".rules." in node.module
            for alias in node.names
        }
        asserted.update(
            imports[call.func.id]
            for statement in ast.walk(tree)
            if isinstance(statement, ast.Assert)
            for call in ast.walk(statement.test)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id in imports
        )
    assert deterministic <= asserted


def test_fact_contracts_never_store_the_rule_answer() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    for rule in catalog.rules:
        first = next(iter(rule.signature.parameters.values()))
        required = fact_type(rule.hints[first.name])
        assert rule.qualname.rsplit(".", 1)[-1] not in required.model_fields


def test_no_rule_only_forwards_a_provider_verdict() -> None:
    """Reject a rule whose whole body reads back a decision a provider already made.

    A body such as ``sum(call.has_round_trip for call in subject.calls)`` computes nothing: the
    finding was made inside the provider and one Boolean field carries the verdict across. A rule
    has to reach its own answer from primitive evidence. Returning a measured quantity such as
    `implementation_lines` stays legitimate, because reporting a measurement is what those rules
    exist to do, so only a forwarded Boolean counts as a contract failure here.
    """
    rule_root = Path(__file__).parents[1] / "src" / "mcmr" / "rules"
    verdict_prefixes = ("is_", "has_", "can_", "should_", "proves_", "only_", "all_", "wraps_")
    forwarding: dict[str, str] = {}
    for path in rule_root.rglob("r[0-9][0-9][0-9][0-9].py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            answer = node.value
            if (
                isinstance(answer, ast.Call)
                and isinstance(answer.func, ast.Name)
                and answer.func.id in {"sum", "any", "all"}
                and isinstance(answer.args[0], ast.GeneratorExp)
            ):
                answer = answer.args[0].elt
            if isinstance(answer, ast.UnaryOp) and isinstance(answer.op, ast.Not):
                answer = answer.operand
            if isinstance(answer, ast.Attribute) and answer.attr.startswith(verdict_prefixes):
                forwarding[str(path.relative_to(rule_root))] = answer.attr
    assert not forwarding


def test_provider_answer_shortcut_does_not_exist() -> None:
    """Reject a call that asks a provider for the answer instead of computing one.

    This reads the syntax rather than the characters, because the four characters also spell a
    Node import inside a script this package embeds, and a guard that a source file can trip by
    quoting another language is a guard nobody trusts twice.
    """
    package = Path(__file__).parents[1] / "src" / "mcmr"
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


def test_every_rule_parameter_contributes_to_its_implementation() -> None:
    rule_root = Path(__file__).parents[1] / "src" / "mcmr" / "rules"
    unused: dict[str, set[str]] = {}
    for path in rule_root.rglob("r[0-9][0-9][0-9][0-9].py"):
        tree = ast.parse(path.read_text())
        functions = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and any(
                isinstance(item, ast.Name) and item.id == "rule" for item in node.decorator_list
            )
        ]
        for function in functions:
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
            if missing := parameters - loaded:
                unused[str(path.relative_to(rule_root))] = missing
    assert not unused


def test_rule_returns_do_not_coerce_predicates_into_counts() -> None:
    rule_root = Path(__file__).parents[1] / "src" / "mcmr" / "rules"
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
