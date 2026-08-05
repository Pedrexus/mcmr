from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import DirectoryFact
from mcmr.kernel import Kernel
from mcmr.project import locate
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.general import (
    directory_module_count,
    directory_pathway,
    empty_directories,
    package_depth,
)
from mcmr.table import AnalysisSession

if TYPE_CHECKING:
    from mcmr.plugins import Fact, Table

_ROOT = Path(__file__).parents[2]
_BINARY = locate(_ROOT)
needs_kernel = pytest.mark.skipif(not _BINARY.exists(), reason="the analysis kernel is not built")


def query[Family: Fact](
    rule: RuleContract,
    subject: Table[Family],
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one deterministic rule once over a complete native table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic kernel test rule returned a model query")
    return result


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Write one repository whose directory shape every count below is computed from by hand.

    Three of these folders hold no unignored entry. One is a leftover, one holds only a cache Git
    ignores, and one carries a dotted name. A fourth holds a placeholder but no source file, so a
    provider deriving directories from parsed files would still meet none of them.
    """
    for relative in ("src/shop", "src/shop/orders", "src/shop/orders/commands"):
        (tmp_path / relative).mkdir(parents=True)
        (tmp_path / relative / "__init__.py").write_text("")
    (tmp_path / "src/shop/catalog").mkdir()
    for relative, source in {
        "src/shop/orders/commands/create.py": "def create() -> int:\n    return 1\n",
        "src/shop/orders/commands/cancel.py": "def cancel() -> int:\n    return 2\n",
        "src/shop/catalog/item.py": "class Item:\n    name = ''\n",
        "src/shop/catalog/price.py": "class Price:\n    amount = 0\n",
        "src/shop/catalog/tax.py": "class Rate:\n    value = 0\n\n\nclass Band:\n    top = 1\n",
    }.items():
        (tmp_path / relative).write_text(source)
    for relative in ("fixtures", "leftover", ".cache"):
        (tmp_path / relative).mkdir()
    (tmp_path / "fixtures/.gitkeep").write_text("")
    (tmp_path / ".gitignore").write_text("__pycache__/\n")
    (tmp_path / "logs/__pycache__").mkdir(parents=True)
    (tmp_path / "logs/__pycache__/stale.pyc").write_text("")
    return tmp_path


def directories(root: Path) -> dict[str, DirectoryFact]:
    """Return every directory fact the kernel built for one repository, keyed by its path."""
    workspace = Kernel(binary=_BINARY, root=root).build(
        [DirectoryFact.__name__], {DirectoryFact.__name__: DirectoryFact}
    )
    return {fact.span.path: fact for fact in workspace.stream(DirectoryFact)}


def directory_table(root: Path) -> Table[DirectoryFact]:
    """Return every directory as one schema-normalized native table."""
    return AnalysisSession(
        root,
        typed_families=[DirectoryFact],
    ).table(DirectoryFact)


def directory_values(
    rule: RuleContract,
    subject: Table[DirectoryFact],
    **settings: RuleSetting,
) -> dict[str, RuleValue]:
    """Return path-keyed values from one repository-wide directory query."""
    facts = subject.facts().select("fact_id", "path")
    rows = query(rule, subject, **settings).values.collect().join(facts.collect(), on="fact_id")
    return {
        cast("str", row["path"]): scalar_row_value(row)
        for row in cast("list[dict[str, RuleValue | None]]", rows.to_dicts())
    }


@needs_kernel
def test_the_directory_family_describes_the_tree_rather_than_the_files_parsed(tree: Path) -> None:
    """Every count is hand-computed from the fixture, including the folders holding no source.

    Only families the request names come back, so the module family the directory counts lean on
        is built and dropped again rather than arriving as a stream nobody asked for. The ignored
        cache is not among the answers, since a directory Git removes is never scanned.
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
    assert [facts["."].entry_count, facts["."].direct_module_count] == [6, 0]
    assert [facts["src"].entry_count, facts["src"].direct_directory_count] == [1, 1]
    assert [facts["src/shop"].entry_count, facts["src/shop"].direct_directory_count] == [3, 2]
    assert facts["src/shop"].direct_file_count == 0
    assert facts["src/shop"].direct_module_count == 0
    assert facts["src/shop/orders/commands"].entry_count == 3
    assert facts["src/shop/catalog"].direct_module_count == 3
    assert all(fact.language is None for fact in facts.values())


@needs_kernel
def test_the_empty_directory_rule_fires_on_what_a_reader_would_call_empty(tree: Path) -> None:
    """Three folders hold nothing, while the placeholder is itself an ordinary entry.

    `logs` holds only the cache Git ignores, which is what makes it empty rather than what makes
    it quiet.
    """
    facts = directories(tree)
    answers = directory_values(empty_directories, directory_table(tree))

    assert {path for path, value in answers.items() if value} == {
        ".cache",
        "leftover",
        "logs",
    }
    assert [facts["fixtures"].entry_count, facts["logs"].entry_count] == [1, 0]
    assert facts[".cache"].entry_count == 0


@needs_kernel
def test_package_depth_counts_the_levels_below_the_source_root(tree: Path) -> None:
    """`src` is the source root here, so depth is measured from it rather than from the root."""
    answers = directory_values(package_depth, directory_table(tree))

    assert answers["."] == 0
    assert answers["src"] == 0
    assert answers["src/shop"] == 1
    assert answers["src/shop/catalog"] == 2
    assert answers["src/shop/orders/commands"] == 3


@needs_kernel
def test_a_directory_pathway_ignores_the_package_initializer(tree: Path) -> None:
    """Only non-root directories that lead through one child are pathways."""
    answers = directory_values(directory_pathway, directory_table(tree))

    assert {path for path, value in answers.items() if value} == {"src/shop/orders"}


@needs_kernel
def test_the_module_count_rule_exempts_catalogs_until_policy_says_otherwise(tree: Path) -> None:
    """A catalog is measured as zero by default, and one explicit setting takes that back.

    The default the docstring describes and the default the signature declared once disagreed, so
    both readings are pinned here against the same fixture.
    """
    facts = directories(tree)
    catalog = facts["src/shop/orders/commands"]
    subject = directory_table(tree)
    default = directory_values(directory_module_count, subject)
    counted = directory_values(
        directory_module_count,
        subject,
        allow_definition_catalogs=False,
    )

    assert catalog.is_definition_catalog
    assert default["src/shop/orders/commands"] == 0
    assert counted["src/shop/orders/commands"] == 2
    assert not facts["src/shop/catalog"].is_definition_catalog
    assert default["src/shop/catalog"] == 3


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
    assert facts["services"].entry_count == 7
    assert facts["services/payments"].direct_module_count == 0
    assert {fact.direct_module_count for fact in facts.values()} == {0, 6}
