from typing import Literal

from mcmr.facts import SourceSpan, SymbolReach, SymbolReachFact, Visibility
from mcmr.rules.general import (
    file_local_public_declaration,
    repository_wide_declaration,
    unreferenced_public_declaration,
)
from mcmr.rules.python import attribute_visibility

from ..support import query_value, retained_query

type DeclarationKind = Literal["class", "function", "method", "property", "variable", "attribute"]
type DeclarationForm = Literal["module", "nested", "decorated"]

_SPAN = SourceSpan(path="src/service.py")


def module(*declarations: SymbolReach, is_test_module: bool = False) -> SymbolReachFact:
    """Build the reach summary of one module."""
    return SymbolReachFact(
        key="reach:service",
        span=_SPAN,
        language="python",
        is_test_module=is_test_module,
        declarations=list(declarations),
    )


def declaration(
    name: str,
    *,
    kind: DeclarationKind = "function",
    form: DeclarationForm = "module",
    visibility: Visibility = Visibility.PUBLIC,
    own_file_references: int = 0,
    other_file_references: int = 0,
    referencing_files: int = 0,
    referencing_directories: int = 0,
    referencing_packages: int = 0,
    owner_visibility: Visibility = Visibility.PUBLIC,
    owner_has_inheritance: bool = False,
    owner_references: int = 0,
    non_owner_references: int = 0,
    unresolved_name_references: int = 0,
) -> SymbolReach:
    """Build one declaration and the spread of what reaches it."""
    return SymbolReach(
        qualname=name,
        kind=kind,
        span=SourceSpan(path="src/service.py", start_line=7),
        is_module_scope=form != "nested",
        is_decorated=form == "decorated",
        visibility=visibility,
        owner_visibility=owner_visibility,
        owner_has_inheritance=owner_has_inheritance,
        own_file_references=own_file_references,
        other_file_references=other_file_references,
        owner_references=owner_references,
        non_owner_references=non_owner_references,
        unresolved_name_references=unresolved_name_references,
        referencing_files=referencing_files,
        referencing_directories=referencing_directories,
        referencing_packages=referencing_packages,
    )


def test_a_public_method_with_complete_owner_only_usage_is_non_public() -> None:
    """Usage proves privacy only after every ambiguity and contract escape is absent."""
    subject = module(
        declaration(
            "service._Parser.parse",
            kind="method",
            owner_visibility=Visibility.INTERNAL,
            owner_references=2,
        ),
        declaration(
            "service._Parser.render",
            kind="method",
            owner_visibility=Visibility.INTERNAL,
            owner_references=1,
            non_owner_references=1,
        ),
        declaration(
            "service._Parser.read",
            kind="method",
            owner_visibility=Visibility.INTERNAL,
            owner_references=1,
            unresolved_name_references=1,
        ),
        declaration(
            "service._Parser.run",
            kind="method",
            owner_visibility=Visibility.INTERNAL,
            owner_references=1,
            owner_has_inheritance=True,
        ),
        declaration("service.Parser.write", kind="method", owner_references=1),
        declaration(
            "service._Parser.missing",
            kind="method",
            owner_visibility=Visibility.INTERNAL,
        ),
    )

    query = retained_query(subject, attribute_visibility)
    assert query_value(query) == 1
    assert query.findings is not None
    finding = query.findings.rows.collect().row(0, named=True)
    assert "_Parser.parse" in finding["message"]
    assert finding["measurement_values"] == [2.0, 0.0, 0.0]


def test_a_public_declaration_nothing_reaches_is_reported() -> None:
    """A public name is a promise, and a promise nobody took up is dead weight."""
    subject = module(
        declaration("service.parse"),
        declaration("service.render", own_file_references=1),
        declaration("service.helper", visibility=Visibility.INTERNAL),
        declaration("service.limit", kind="variable"),
    )

    query = retained_query(subject, unreferenced_public_declaration)
    assert query_value(query) == 1
    assert query.findings is not None
    finding = query.findings.rows.collect().row(0, named=True)
    assert finding["start_line"] == 7
    assert "service.parse" in finding["message"]
    assert (
        query_value(
            retained_query(
                module(declaration("service.parse"), is_test_module=True),
                unreferenced_public_declaration,
            )
        )
        == 0
    )
    assert (
        query_value(
            retained_query(
                module(declaration("s.f.nested", form="nested")),
                unreferenced_public_declaration,
            )
        )
        == 0
    )


def test_a_public_declaration_only_its_own_file_reaches_is_reported() -> None:
    """A name published to the repository and used in one place states a contract it lacks."""
    subject = module(
        declaration("service.parse", own_file_references=3),
        declaration("service.render", own_file_references=1, other_file_references=2),
        declaration("service.missing"),
        declaration("service.limit", kind="attribute", own_file_references=2),
        declaration("service.outer.inner", own_file_references=2, form="nested"),
        declaration("service.registered", own_file_references=2, form="decorated"),
    )

    query = retained_query(subject, file_local_public_declaration)
    assert query_value(query) == 1
    assert query.findings is not None
    assert query.findings.rows.collect().item(0, "start_line") == 7
    assert (
        query_value(
            retained_query(
                module(
                    declaration("service.parse", own_file_references=3),
                    is_test_module=True,
                ),
                file_local_public_declaration,
            )
        )
        == 0
    )


def test_a_declaration_spreading_past_the_ceiling_is_reported() -> None:
    """Spread is not a defect, it is the evidence that names the real contracts."""
    subject = module(
        declaration(
            "service.Model",
            kind="class",
            referencing_packages=6,
            referencing_directories=4,
            referencing_files=9,
        ),
        declaration("service.parse", referencing_packages=3),
        declaration("service.render", referencing_packages=1, referencing_files=9),
    )

    query = retained_query(subject, repository_wide_declaration)
    assert query_value(query) == 1
    assert query.findings is not None
    finding = query.findings.rows.collect().row(0, named=True)
    assert finding["start_line"] == 7
    assert finding["measurement_values"][0] == 6.0
    assert (
        query_value(retained_query(subject, repository_wide_declaration, maximum_packages=6)) == 0
    )
    assert query_value(retained_query(module(), repository_wide_declaration)) == 0
