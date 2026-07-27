import subprocess
from pathlib import Path

import pytest

from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.facts import (
    AlertFact,
    CallFact,
    ClassFact,
    DirectoryFact,
    FunctionFact,
    ImportBindingFact,
    ModuleFact,
    RunbookFact,
)
from mcmr.kernel import EvidenceStore, Kernel, Workspace, locate, requested_fact
from mcmr.rules.general.deterministic.filesystem.r0001 import empty_directories
from mcmr.rules.general.deterministic.filesystem.r0002 import package_depth
from mcmr.rules.general.deterministic.filesystem.r0003 import directory_module_count
from mcmr.rules.python.deterministic.imports.r0003 import unused_import

ROOT = Path(__file__).parents[1]
BINARY = locate(ROOT)


def kernel_missing() -> bool:
    """Whether this checkout has no kernel binary to talk to."""
    return not BINARY.exists()


needs_kernel = pytest.mark.skipif(kernel_missing(), reason="the analysis kernel is not built")


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Write one small repository the kernel can analyze."""
    (tmp_path / "sample.py").write_text(
        'import json\nimport os\nfrom pathlib import Path\n\n__all__ = ["Path"]\n\n\n'
        "class Loader:\n"
        "    limit: int = 3\n\n"
        "    def load(self, name: str) -> str:\n"
        "        if name:\n"
        "            return json.dumps({'name': name})\n"
        "        return ''\n"
    )
    return tmp_path


def test_the_planner_requests_only_the_families_its_rules_read() -> None:
    """A family no selected rule names is never asked for."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    rules = [rule for rule in catalog.rules if rule.qualname == "unused_import"]
    kernel = Kernel(binary=BINARY, root=ROOT)

    assert kernel.requested(rules) == {"ImportBindingFact": ImportBindingFact}
    assert kernel.requested([]) == {}
    assert requested_fact(rules[0]) is ImportBindingFact


def test_an_empty_request_never_starts_the_kernel() -> None:
    """With nothing to build there is no process to run and no workspace to fill."""
    workspace = Kernel(binary=Path("mcmr-kernel-that-does-not-exist"), root=ROOT).run([])

    assert workspace.streams == {}
    assert workspace.stats.file_count == 0


@needs_kernel
def test_the_kernel_builds_the_facts_its_families_name(repository: Path) -> None:
    """Every requested family arrives as validated facts, and nothing else does."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    families = {ImportBindingFact, ModuleFact, ClassFact, FunctionFact, CallFact}
    rules = [rule for rule in catalog.rules if requested_fact(rule) in families]
    workspace = Kernel(binary=BINARY, root=repository).run(rules)

    assert set(workspace.streams) == families
    assert workspace.stats.file_count == 1
    assert workspace.stats.parse_failure_count == 0

    bindings = workspace.stream(ImportBindingFact)
    assert {binding.name for binding in bindings} == {"json", "os", "Path"}
    assert [binding.reference_count for binding in bindings if binding.name == "json"] == [1]

    module = workspace.stream(ModuleFact)[0]
    assert module.class_count == 1
    assert module.physical_line_count == 14

    analysis = workspace.stream(ClassFact)[0].classes[0]
    assert analysis.name == "Loader"
    assert analysis.field_count == 1
    assert [method.name for method in analysis.methods] == ["load"]

    function = workspace.stream(FunctionFact)[0]
    assert function.name == "load"
    assert function.scope == "method"
    assert [increment.kind for increment in function.control_increments] == ["conditional"]


@needs_kernel
def test_the_unused_import_rule_agrees_with_ruff(repository: Path) -> None:
    """The kernel and Ruff name the same unused imports in the same file.

    Ruff owns this check, which is exactly why it is the oracle: an unused import is unambiguous,
    so any disagreement is a defect in the kernel's reference counting rather than a matter of
    policy.
    """
    workspace = Kernel(binary=BINARY, root=repository).run(
        [
            rule
            for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
            if rule.qualname == "unused_import"
        ]
    )
    found = {
        binding.name
        for binding in workspace.stream(ImportBindingFact)
        if unused_import(binding).value
    }
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
def test_an_exclusion_set_reaches_the_kernel(repository: Path) -> None:
    """A caller's exclusions travel with the request, so an excluded file is never read."""
    rules = [
        rule
        for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
        if rule.qualname == "unused_import"
    ]
    workspace = Kernel(binary=BINARY, root=repository, exclude=("**/sample.py",)).run(rules)

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
    workspace = Kernel(binary=BINARY, root=tmp_path, suffixes=(".ts",)).run(rules)
    analysis = workspace.stream(ClassFact)[0].classes[0]

    assert analysis.name == "Engine"
    assert [method.name for method in analysis.methods] == ["run"]


@needs_kernel
def test_a_stale_protocol_version_is_refused(repository: Path, tmp_path: Path) -> None:
    """A kernel speaking another protocol fails loudly instead of feeding stale facts."""
    stub = tmp_path / "stub"
    stub.write_text('#!/bin/sh\necho \'{"version": 99, "facts": {}, "stats": {}}\'\n')
    stub.chmod(0o755)
    rules = [
        rule
        for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
        if rule.qualname == "unused_import"
    ]

    with pytest.raises(RuntimeError, match="protocol 99"):
        Kernel(binary=stub, root=repository).run(rules)


@needs_kernel
def test_a_failing_kernel_reports_its_own_message(tmp_path: Path) -> None:
    """The kernel's diagnostic reaches the caller rather than an empty workspace."""
    stub = tmp_path / "stub"
    stub.write_text("#!/bin/sh\necho 'the root does not exist' >&2\nexit 1\n")
    stub.chmod(0o755)
    rules = [
        rule
        for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
        if rule.qualname == "unused_import"
    ]

    with pytest.raises(RuntimeError, match="the root does not exist"):
        Kernel(binary=stub, root=tmp_path).run(rules)


def test_the_workspace_runs_only_the_rules_it_holds_facts_for() -> None:
    """A rule whose stream the kernel did not build never reaches the engine."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    rules = [
        rule for rule in catalog.rules if rule.qualname in {"unused_import", "module_line_count"}
    ]
    workspace = Workspace(streams={ImportBindingFact: []})

    assert [rule.qualname for rule in workspace.runnable(rules)] == ["unused_import"]


def test_the_binary_falls_back_to_the_path_when_nothing_is_built(tmp_path: Path) -> None:
    """Without a local build the client asks the path for the kernel."""
    assert locate(tmp_path) == Path("mcmr-kernel")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Write one repository whose directory shape every count below is computed from by hand.

    Four of these folders hold nothing a reader would find. One is a leftover, one holds a
    placeholder saying its emptiness is deliberate, one holds only a cache the exclusion set
    removes, and one carries a dotted name that says it is machinery. None of them holds a source
    file, so a provider deriving directories from the files it parsed would meet none of them.
    """
    for relative in ("src/shop", "src/shop/orders", "src/shop/orders/commands"):
        (tmp_path / relative).mkdir(parents=True)
        (tmp_path / relative / "__init__.py").write_text("")
    (tmp_path / "src/shop/orders/commands/create.py").write_text(
        "def create() -> int:\n    return 1\n"
    )
    (tmp_path / "src/shop/orders/commands/cancel.py").write_text(
        "def cancel() -> int:\n    return 2\n"
    )
    (tmp_path / "src/shop/catalog").mkdir()
    (tmp_path / "src/shop/catalog/item.py").write_text("class Item:\n    name = ''\n")
    (tmp_path / "src/shop/catalog/price.py").write_text("class Price:\n    amount = 0\n")
    (tmp_path / "src/shop/catalog/tax.py").write_text(
        "class Rate:\n    value = 0\n\n\nclass Band:\n    top = 1\n"
    )
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures/.gitkeep").write_text("")
    (tmp_path / "leftover").mkdir()
    (tmp_path / "logs/__pycache__").mkdir(parents=True)
    (tmp_path / "logs/__pycache__/stale.pyc").write_text("")
    (tmp_path / ".cache").mkdir()
    return tmp_path


def directories(root: Path) -> dict[str, DirectoryFact]:
    """Return every directory fact the kernel built for one repository, keyed by its path."""
    workspace = Kernel(binary=BINARY, root=root).build(
        [DirectoryFact.__name__], {DirectoryFact.__name__: DirectoryFact}
    )
    return {fact.span.path: fact for fact in workspace.stream(DirectoryFact)}


@needs_kernel
def test_the_directory_family_describes_the_tree_rather_than_the_files_parsed(tree: Path) -> None:
    """Every count is hand-computed from the fixture, including the folders holding no source.

    Only families the request names come back, so the module family the directory counts lean on
    is built and dropped again rather than arriving as a stream nobody asked for. The excluded
    cache is not among the answers, since a directory the exclusion set removes is never scanned.
    """
    facts = directories(tree)

    assert set(facts) == {
        ".",
        ".cache",
        "src",
        "src/shop",
        "src/shop/catalog",
        "src/shop/orders",
        "src/shop/orders/commands",
        "fixtures",
        "leftover",
        "logs",
    }
    assert [facts["."].visible_entry_count, facts["."].direct_module_count] == [4, 0]
    assert facts["."].is_ignored is False
    assert [facts["src"].visible_entry_count, facts["src"].direct_module_count] == [1, 0]
    assert [facts["src/shop"].visible_entry_count, facts["src/shop"].direct_module_count] == [3, 1]
    assert facts["src/shop/orders/commands"].visible_entry_count == 3
    assert facts["src/shop/catalog"].direct_module_count == 3
    assert all(fact.language is None for fact in facts.values())


@needs_kernel
def test_the_empty_directory_rule_fires_on_what_a_reader_would_call_empty(tree: Path) -> None:
    """Four folders hold nothing, and only the two nobody decided about are reported.

    `logs` holds only the cache the exclusion set removes, which is what makes it empty rather
    than what makes it quiet.
    """
    facts = directories(tree)

    assert {path for path, fact in facts.items() if empty_directories(fact)} == {
        "leftover",
        "logs",
    }
    assert facts["fixtures"].is_retained
    assert facts[".cache"].is_ignored
    assert [facts["logs"].visible_entry_count, facts[".cache"].visible_entry_count] == [0, 0]


@needs_kernel
def test_package_depth_counts_the_levels_below_the_source_root(tree: Path) -> None:
    """`src` is the source root here, so depth is measured from it rather than from the root."""
    facts = directories(tree)

    assert package_depth(facts["."]) == 0
    assert package_depth(facts["src"]) == 0
    assert package_depth(facts["src/shop"]) == 1
    assert package_depth(facts["src/shop/catalog"]) == 2
    assert package_depth(facts["src/shop/orders/commands"]) == 3


@needs_kernel
def test_the_module_count_rule_exempts_a_catalog_and_measures_everything_else(tree: Path) -> None:
    """Every module under `commands` declares one thing and one under `catalog` declares two."""
    facts = directories(tree)
    catalog = facts["src/shop/orders/commands"]

    assert catalog.is_definition_catalog
    assert directory_module_count(catalog) == 0
    assert directory_module_count(catalog, allow_definition_catalogs=False) == 3
    assert not facts["src/shop/catalog"].is_definition_catalog
    assert directory_module_count(facts["src/shop/catalog"]) == 3


@needs_kernel
def test_one_directory_answers_once_however_many_files_it_holds(tmp_path: Path) -> None:
    """A provider counting per file rather than per directory cannot pass this.

    The defect this replaces emitted one fact per source file, each stating that its directory
    held one entry and one module, so a folder of six siblings answered six times with the same
    hardcoded pair and a folder holding nothing never answered at all.
    """
    (tmp_path / "services").mkdir()
    for name in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta"):
        (tmp_path / "services" / f"{name}.py").write_text("value = 1\n")
    (tmp_path / "services/payments").mkdir()

    facts = directories(tmp_path)

    assert sorted(facts) == [".", "services", "services/payments"]
    assert facts["services"].direct_module_count == 6
    assert facts["services"].visible_entry_count == 7
    assert facts["services/payments"].direct_module_count == 0
    assert {fact.direct_module_count for fact in facts.values()} == {0, 6}


def test_retained_evidence_reaches_the_rules_that_read_it(tmp_path: Path) -> None:
    """A fact no parser can derive arrives as a record the project keeps."""
    records = tmp_path / ".mcmr"
    records.mkdir()
    (records / "RunbookFact.json").write_text(
        '{"key": "runbook:deploy", "span": {"path": "docs/runbook.md"}, '
        '"triggers": [{"name": "rollback", "checks": {"exercised": true}}]}'
    )

    streams = EvidenceStore(directory=records).streams([RunbookFact, AlertFact])
    retained = Workspace(streams=streams).stream(RunbookFact)

    assert set(streams) == {RunbookFact}
    assert retained[0].triggers.coverage("exercised") == 100.0


def test_a_record_file_may_hold_one_fact_or_several(tmp_path: Path) -> None:
    """One object and a list of them are both valid, so a project writes whichever fits."""
    records = tmp_path / ".mcmr"
    records.mkdir()
    (records / "AlertFact.json").write_text(
        '[{"key": "alert:one", "span": {"path": "ops.yaml"}}, '
        '{"key": "alert:two", "span": {"path": "ops.yaml"}}]'
    )

    streams = EvidenceStore(directory=records).streams([AlertFact])

    assert len(Workspace(streams=streams).stream(AlertFact)) == 2
