from typing import Literal

from mcmr.facts import SourceSpan, SymbolReach, SymbolReachFact, Visibility
from mcmr.rules.general.deterministic.reach.r0001 import unreferenced_public_declaration
from mcmr.rules.general.deterministic.reach.r0002 import file_local_public_declaration
from mcmr.rules.general.deterministic.reach.r0003 import repository_wide_declaration

type DeclarationKind = Literal["class", "function", "method", "property", "variable", "attribute"]

SPAN = SourceSpan(path="src/service.py")


def module(*declarations: SymbolReach, is_test_module: bool = False) -> SymbolReachFact:
    """Build the reach summary of one module."""
    return SymbolReachFact(
        key="reach:service",
        span=SPAN,
        is_test_module=is_test_module,
        declarations=list(declarations),
    )


def declaration(
    name: str,
    *,
    kind: DeclarationKind = "function",
    is_module_scope: bool = True,
    is_decorated: bool = False,
    visibility: Visibility = Visibility.PUBLIC,
    own_file_references: int = 0,
    other_file_references: int = 0,
    referencing_files: int = 0,
    referencing_packages: int = 0,
) -> SymbolReach:
    """Build one declaration and the spread of what reaches it."""
    return SymbolReach(
        qualname=name,
        kind=kind,
        is_module_scope=is_module_scope,
        is_decorated=is_decorated,
        visibility=visibility,
        own_file_references=own_file_references,
        other_file_references=other_file_references,
        referencing_files=referencing_files,
        referencing_packages=referencing_packages,
    )


def test_a_public_declaration_nothing_reaches_is_reported() -> None:
    """A public name is a promise, and a promise nobody took up is dead weight."""
    subject = module(
        declaration("service.parse"),
        declaration("service.render", own_file_references=1),
        declaration("service.helper", visibility=Visibility.INTERNAL),
        declaration("service.limit", kind="variable"),
    )

    assert unreferenced_public_declaration(subject) == 1
    assert (
        unreferenced_public_declaration(module(declaration("service.parse"), is_test_module=True))
        == 0
    )
    assert (
        unreferenced_public_declaration(module(declaration("s.f.nested", is_module_scope=False)))
        == 0
    )


def test_a_public_declaration_only_its_own_file_reaches_is_reported() -> None:
    """A name published to the repository and used in one place states a contract it lacks."""
    subject = module(
        declaration("service.parse", own_file_references=3),
        declaration("service.render", own_file_references=1, other_file_references=2),
        declaration("service.missing"),
        declaration("service.limit", kind="attribute", own_file_references=2),
    )

    assert file_local_public_declaration(subject).value == 1
    assert (
        file_local_public_declaration(
            module(declaration("service.parse", own_file_references=3), is_test_module=True)
        ).value
        == 0
    )


def test_a_declaration_spreading_past_the_ceiling_is_reported() -> None:
    """Spread is not a defect, it is the evidence that names the real contracts."""
    subject = module(
        declaration("service.Model", kind="class", referencing_packages=6),
        declaration("service.parse", referencing_packages=3),
        declaration("service.render", referencing_packages=1, referencing_files=9),
    )

    assert repository_wide_declaration(subject) == 1
    assert repository_wide_declaration(subject, maximum_packages=6) == 0
    assert repository_wide_declaration(module()) == 0
