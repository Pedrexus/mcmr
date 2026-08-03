import subprocess
from pathlib import Path
from typing import cast

import pytest

from mcmr.facts import (
    CallFact,
    ClassFact,
    Fact,
    FunctionFact,
    ImportBindingFact,
    ModuleFact,
)
from mcmr.kernel import (
    Kernel,
    locate,
    requested_fact,
)
from mcmr.query import RuleQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.rules.python import unused_import
from mcmr.table import AnalysisSession, ImportBindingRelation, Table

_ROOT = Path(__file__).parents[2]
_BINARY = locate(_ROOT)


def is_kernel_missing() -> bool:
    """Whether this checkout has no kernel binary to talk to."""
    return not _BINARY.exists()


needs_kernel = pytest.mark.skipif(is_kernel_missing(), reason="the analysis kernel is not built")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Write one small repository the kernel can analyze."""
    (tmp_path / "sample.py").write_text(
        """import json
import os
from pathlib import Path

__all__ = ["Path"]


class Loader:
    limit: int = 3

    def load(self, name: str) -> str:
        if name:
            return json.dumps({'name': name})
        return ''
"""
    )
    return tmp_path


def test_the_planner_requests_only_the_families_its_rules_read() -> None:
    """A family no selected rule names is never asked for."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    rules = [rule for rule in catalog.rules if rule.qualname == "unused_import"]
    kernel = Kernel(binary=_BINARY, root=_ROOT)

    assert kernel.requested(rules) == {"ImportBindingFact": ImportBindingFact}
    assert kernel.requested([]) == {}
    assert requested_fact(rules[0]) is ImportBindingFact


def test_an_empty_request_never_starts_the_kernel() -> None:
    """With nothing to build there is no process to run and no workspace to fill."""
    workspace = Kernel(binary=Path("mcmr-kernel-that-does-not-exist"), root=_ROOT).run([])

    assert workspace.streams == {}
    assert workspace.stats.file_count == 0


@needs_kernel
def test_the_kernel_builds_the_facts_its_families_name(repository: Path) -> None:
    """Every requested family arrives as validated facts, and nothing else does."""

    def evidence() -> tuple[set[str], list[int], tuple, tuple, tuple, tuple]:
        """Return the complete evidence contract from this one workspace."""
        bindings = workspace.stream(ImportBindingFact)
        module = workspace.stream(ModuleFact)[0]
        analysis = workspace.stream(ClassFact)[0].classes[0]
        function = workspace.stream(FunctionFact)[0]
        call = workspace.stream(CallFact)[0].calls[0]
        return (
            {binding.name for binding in bindings},
            [binding.reference_count for binding in bindings if binding.name == "json"],
            (module.class_count, module.physical_line_count, module.statement_count),
            (analysis.name, analysis.field_count, [method.name for method in analysis.methods]),
            (function.name, function.scope, [item.kind for item in function.control_increments]),
            (call.qualified_name, call.is_external, call.is_standard_library, call.is_first_party),
        )

    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    families = {ImportBindingFact, ModuleFact, ClassFact, FunctionFact, CallFact}
    rules = [rule for rule in catalog.rules if requested_fact(rule) in families]
    workspace = Kernel(binary=_BINARY, root=repository).run(rules)
    required = {family for rule in rules for _, family in rule.tables}

    assert (
        set(workspace.streams),
        workspace.stats.file_count,
        workspace.stats.parse_failure_count,
    ) == (required, 1, 0)
    assert workspace.stats.total_nanoseconds >= workspace.stats.extraction_nanoseconds

    assert evidence() == (
        {"json", "os", "Path"},
        [1],
        (1, 14, 10),
        ("Loader", 1, ["load"]),
        ("load", "method", ["conditional"]),
        ("json.dumps", True, True, False),
    )


@needs_kernel
def test_call_resolution_uses_the_repository_graph_and_runtime_standard_library(
    tmp_path: Path,
) -> None:
    """Aliases, local declarations, builtins, and third parties get distinct call evidence."""
    (tmp_path / "calls.py").write_text(
        """import asyncio as aio
import third_party as third

def local() -> None:
    pass

def run() -> None:
    aio.run(work())
    third.convert(value)
    local()
    tuple(values)
"""
    )

    workspace = Kernel(binary=_BINARY, root=tmp_path).build(
        [CallFact.__name__], {CallFact.__name__: CallFact}
    )
    calls = {call.qualified_name: call for call in workspace.stream(CallFact)[0].calls}

    assert calls["asyncio.run"].is_standard_library
    assert calls["third_party.convert"].is_external
    assert not calls["third_party.convert"].is_standard_library
    assert calls["calls.local"].is_first_party
    assert calls["builtins.tuple"].is_standard_library


@needs_kernel
def test_the_unused_import_rule_agrees_with_ruff(repository: Path) -> None:
    """The kernel and Ruff name the same unused imports in the same file.

    Ruff owns this check, which is exactly why it is the oracle: an unused import is unambiguous,
    so any disagreement is a defect in the kernel's reference counting rather than a matter of
    policy.
    """
    bindings = AnalysisSession(
        repository,
        suffixes=[".py"],
        typed_families=[ImportBindingFact.__name__],
    ).import_binding_tables()
    result = unused_import.invoke_table(
        cast("Table[Fact]", bindings), settings={}, dependencies={}
    )
    assert isinstance(result, RuleQuery)
    values = result.values.collect()
    found = set(
        values.filter(values["boolean_value"])
        .join(
            bindings.frame(ImportBindingRelation.FACTS).select("fact_id", "name"),
            on="fact_id",
        )
        .get_column("name")
    )
    oracle = subprocess.run(
        [
            "ruff",
            "check",
            "--select",
            "F401",
            "--no-cache",
            "--isolated",
            "--output-format",
            "concise",
            str(repository),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    reported = {
        line.split("`")[1] for line in oracle.stdout.splitlines() if "F401" in line and "`" in line
    }

    assert found == {"os"}
    assert found == reported


@needs_kernel
def test_gitignore_reaches_the_kernel(repository: Path) -> None:
    """The repository's ignore policy reaches the kernel, so ignored source is never read."""
    (repository / ".gitignore").write_text("sample.py\n")
    rules = [
        rule
        for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
        if rule.qualname == "unused_import"
    ]
    workspace = Kernel(binary=_BINARY, root=repository).run(rules)

    assert workspace.stats.file_count == 0
    assert workspace.stream(ImportBindingFact) == []


@needs_kernel
def test_a_source_suffix_selects_another_language(tmp_path: Path) -> None:
    """The same families are built from TypeScript, so a general rule reads either language."""
    (tmp_path / "service.ts").write_text(
        "export class Engine {\n  run(): number {\n    return 1;\n  }\n}\n"
    )
    rules = [
        rule
        for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
        if requested_fact(rule) is ClassFact
    ]
    workspace = Kernel(binary=_BINARY, root=tmp_path, suffixes=(".ts",)).run(rules)
    analysis = workspace.stream(ClassFact)[0].classes[0]

    assert analysis.name == "Engine"
    assert [method.name for method in analysis.methods] == ["run"]
