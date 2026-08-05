from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import RuleValue
from mcmr.facts import (
    ExportBypass,
    ExportFact,
    ImportBindingFact,
    NodeRef,
    PublicExport,
    SourceSpan,
)
from mcmr.plugins import RepositoryTables
from mcmr.query import RuleQuery
from mcmr.rules.python import (
    import_module_depth,
    internal_relative_import,
    project_private_import,
    unused_import,
)
from mcmr.table import AnalysisSession

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def scalar(query: RuleQuery, row: int = 0) -> RuleValue:
    """Return one scalar from a direct rule query."""
    values = query.values.collect().row(row, named=True)
    for name in ("boolean_value", "integer_value", "float_value", "category_value"):
        if values[name] is not None:
            return cast("RuleValue", values[name])
    raise TypeError("the rule emitted no scalar value")


def import_queries(root: Path) -> Mapping[str, RuleQuery]:
    """Parse one import corpus once and run its import rules once each."""
    session = AnalysisSession(
        root,
        suffixes=[".py"],
        typed_families=[ImportBindingFact, ExportFact],
    )
    table = session.import_binding_tables()
    tables = RepositoryTables().add(table).add(session.table(ExportFact))
    queries: dict[str, RuleQuery] = {}
    for rule in (
        internal_relative_import,
        project_private_import,
        unused_import,
        import_module_depth,
    ):
        result = (
            rule.invoke(
                tables,
                settings={},
                dependencies={},
            )
            if rule is import_module_depth
            else rule.invoke_table(table, settings={}, dependencies={})
        )
        if not isinstance(result, RuleQuery):
            raise TypeError("a deterministic import rule returned a model query")
        queries[rule.qualname] = result
    return queries


def export_subject() -> ExportFact:
    """Build one public export with a cycle-safe internal bypass."""
    return ExportFact(
        key="export:pkg.Engine",
        span=SourceSpan(path="pkg/__init__.py"),
        public_export=PublicExport(
            name="Engine",
            target="pkg.engine.Engine",
            nodes=[
                NodeRef(
                    id="pkg/__init__.py:11:sequence-item",
                    span=SourceSpan(
                        path="pkg/__init__.py",
                        start_line=1,
                        start_column=11,
                        end_line=1,
                        end_column=19,
                    ),
                    kind="sequence-item",
                    text='"Engine"',
                )
            ],
            span=SourceSpan(path="pkg/__init__.py"),
        ),
        bypasses=[
            ExportBypass(
                public_module="pkg",
                name="Engine",
                target="pkg.engine.Engine",
                expression="pkg.engine.Engine",
                module_node=NodeRef(
                    id="service.py:5:module",
                    span=SourceSpan(
                        path="service.py",
                        start_line=3,
                        start_column=5,
                        end_line=3,
                        end_column=15,
                    ),
                    kind="module",
                    text="pkg.engine",
                ),
                replacement_module="pkg",
                is_cycle_safe=True,
                span=SourceSpan(path="service.py", start_line=3),
            )
        ],
    )
