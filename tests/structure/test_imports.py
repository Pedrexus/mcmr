from typing import TYPE_CHECKING

from mcmr.domain.contracts import FixSafety
from mcmr.facts import (
    DirectoryFact,
    ExportFact,
    ImportBindingFact,
    SourceSpan,
)
from mcmr.plugins import RepositoryTables
from mcmr.query import RuleQuery
from mcmr.rules.general import (
    directory_module_count,
    directory_pathway,
    empty_directories,
    package_depth,
)
from mcmr.rules.python import (
    import_module_depth,
    internal_relative_import,
    project_private_import,
    unused_import,
)
from mcmr.table import AnalysisSession

from ..support import retained_query

if TYPE_CHECKING:
    from pathlib import Path


from .support import import_queries, scalar


def test_project_owned_import_queries_keep_values_and_safe_fixes(tmp_path: Path) -> None:
    package = tmp_path / "acme"
    package.mkdir()
    for name, source in {
        "__init__.py": "",
        "models.py": "class User:\n    pass\n",
        "_engine.py": "def execute():\n    pass\n",
        "service.py": """from acme.models import User
from acme._engine import execute

def build():
    return User(), execute()
""",
    }.items():
        (package / name).write_text(source, encoding="utf-8")
    queries = import_queries(tmp_path)

    relative, private = (
        queries[internal_relative_import.qualname],
        queries[project_private_import.qualname],
    )
    assert relative.fix is not None
    assert (
        relative.values.collect().get_column("boolean_value").sum(),
        set(relative.fix.rewrites.collect().get_column("source")),
        private.values.collect().get_column("boolean_value").sum(),
    ) == (2, {".models", "._engine"}, 1)


def test_unused_import_query_keeps_exemptions_and_review_fix(tmp_path: Path) -> None:
    (tmp_path / "subject.py").write_text(
        """from __future__ import annotations
import json
import os
from math import *

value = os.getcwd()
""",
        encoding="utf-8",
    )
    result = import_queries(tmp_path)[unused_import.qualname]
    values = result.values.collect()
    assert result.findings is not None
    findings = result.findings.rows.collect()
    assert result.fix is not None
    assert (
        values.get_column("boolean_value").sum(),
        findings.height,
        "`json` is imported from `json`" in findings.item(0, "message"),
        unused_import.query_fix_safety,
        result.fix.rewrites.collect().get_column("kind").to_list(),
    ) == (1, 1, True, FixSafety.REVIEW, ["remove"])


def test_unused_import_query_addresses_one_binding_in_a_group(tmp_path: Path) -> None:
    """A grouped import offers an exact binding deletion rather than dropping live siblings."""
    (tmp_path / "subject.py").write_text(
        "import json, os\n\nvalue = os.getcwd()\n",
        encoding="utf-8",
    )

    result = import_queries(tmp_path)[unused_import.qualname]

    assert result.fix is not None
    assert result.fix.nodes.collect().select("kind", "text").row(0) == (
        "sequence-item",
        "json",
    )


def test_empty_directory_and_depth_cases() -> None:
    empty = DirectoryFact(key="directory", span=SourceSpan(path="src/unused"))
    result = retained_query(empty, empty_directories)
    assert result.fix is not None
    assert (
        scalar(result),
        scalar(retained_query(empty.model_copy(update={"entry_count": 1}), empty_directories)),
        scalar(retained_query(empty.model_copy(update={"source_depth": 6}), package_depth)),
        empty_directories.query_fix_safety,
        result.fix.rewrites.collect().item(0, "kind"),
        result.fix.rewrites.collect().item(0, "source"),
    ) == (True, False, 6, FixSafety.SAFE, "remove-directory", "src/unused")
    framework = empty.model_copy(update={"span": SourceSpan(path="src/rules/catalog")})
    assert (
        retained_query(
            framework,
            package_depth,
            framework_roots=["src/rules"],
        )
        .values.collect()
        .is_empty()
    )


def test_directory_module_count_cases() -> None:
    """Definition catalogs sit outside the ordinary direct-module ceiling until policy says no."""
    crowded = DirectoryFact(
        key="directory",
        span=SourceSpan(path="src/catalog"),
        direct_module_count=7,
    )
    catalog = crowded.model_copy(update={"is_definition_catalog": True})
    assert (
        scalar(retained_query(crowded, directory_module_count)),
        scalar(retained_query(catalog, directory_module_count)),
        scalar(
            retained_query(
                catalog,
                directory_module_count,
                allow_definition_catalogs=False,
            )
        ),
    ) == (7, 0, 7)


def test_directory_pathway_cases() -> None:
    """A real lane and a directory with its own file are not navigation-only pathways."""
    pathway = DirectoryFact(
        key="directory",
        span=SourceSpan(path="src/services"),
        source_depth=2,
        direct_directory_count=1,
        only_child_directory="payments",
    )
    lane = pathway.model_copy(
        update={
            "span": SourceSpan(path="src/rules/python"),
            "only_child_directory": "deterministic",
        }
    )
    assert (
        scalar(retained_query(pathway, directory_pathway)),
        scalar(
            retained_query(
                pathway.model_copy(update={"direct_file_count": 1}),
                directory_pathway,
            )
        ),
        scalar(retained_query(lane, directory_pathway)),
    ) == (True, False, False)


def test_import_depth_counts_named_components_without_relative_dots(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "module.py").write_text(
        """from library.internal.transport.http import Client
from ...transport.http import Relative
""",
        encoding="utf-8",
    )

    result = import_queries(tmp_path)[import_module_depth.qualname]

    assert result.values.collect().get_column("integer_value").to_list() == [4, 2]


def test_deep_import_reuses_one_proven_public_facade(tmp_path: Path) -> None:
    """The depth rule fixes only a complete import with an existing cycle-safe public route."""
    (implementation := tmp_path / "library" / "internal" / "transport").mkdir(parents=True)
    (tmp_path / "library" / "__init__.py").write_text(
        'from .internal.transport.http import Client\n\n__all__ = ["Client"]\n'
    )
    (implementation / "http.py").write_text("class Client:\n    pass\n")
    (tmp_path / "consumer.py").write_text(
        "from library.internal.transport.http import Client\n\nclient = Client()\n"
    )
    session = AnalysisSession(
        tmp_path,
        suffixes=[".py"],
        typed_families=[ImportBindingFact, ExportFact],
    )
    imports = session.import_binding_tables()
    tables = RepositoryTables().add(imports).add(session.table(ExportFact))

    result = import_module_depth.invoke(
        tables,
        settings={},
        dependencies={},
    )

    assert isinstance(result, RuleQuery) and result.fix is not None
    assert (
        result.values.collect().get_column("integer_value").max(),
        result.fix.rewrites.collect().select("kind", "source").rows(),
    ) == (4, [("replace", "library")])
