import inspect
from typing import Literal

import pytest

from mcmr import rule
from mcmr.facts import ChecklistItem, ImportBindingFact, NodeRef, SourceSpan, SymbolRef
from mcmr.models import FixSafety, Occurrence, Remove, Replace, SourceRewrite, fact_type


def binding() -> ImportBindingFact:
    """Build one import binding used by contract tests."""
    span = SourceSpan(path="example.py", end_column=11)
    return ImportBindingFact(
        key="module:json",
        span=span,
        name="json",
        module="json",
        declaration=NodeRef(id="import:json", span=span, kind="import", text="import json"),
    )


def node(subject: ImportBindingFact) -> NodeRef:
    """Return the declaration handle a contract fix edits."""
    assert subject.declaration is not None
    return subject.declaration


def test_rule_remains_typed_and_callable() -> None:
    @rule
    def unused_import(subject: ImportBindingFact) -> Occurrence:
        return not subject.has_qualifying_use

    assert unused_import(binding()) is True
    assert unused_import.module == __name__
    assert unused_import.qualname.endswith("unused_import")


@pytest.mark.anyio
async def test_rule_accepts_async_functions() -> None:
    @rule
    async def import_intent(
        subject: ImportBindingFact,
    ) -> Literal["used", "unused"]:
        return "used" if subject.has_qualifying_use else "unused"

    result = import_intent(binding())
    assert inspect.isawaitable(result)
    assert await result == "unused"


def test_rule_declares_zero_or_more_source_linked_fixes() -> None:
    @rule
    def unused_import(subject: ImportBindingFact) -> Occurrence:
        return not subject.has_qualifying_use

    @unused_import.fix(is_default=True)
    def remove_unused_import(subject: ImportBindingFact) -> list[SourceRewrite]:
        """Remove the unused import."""
        return [Remove(target=node(subject))]

    @unused_import.fix(safety=FixSafety.REVIEW)
    def reexport_import(subject: ImportBindingFact) -> list[SourceRewrite]:
        """Make the re-export explicit."""
        return [Replace(target=node(subject), source="from .api import Client as Client")]

    @unused_import.fix(safety=FixSafety.REVIEW)
    def nothing_to_change(subject: ImportBindingFact) -> list[SourceRewrite]:
        """Leave a binding this fix cannot repair."""
        return []

    plan = remove_unused_import(binding())
    assert plan is not None
    assert plan.summary == "Remove the unused import."
    assert reexport_import(binding()) is not None
    assert nothing_to_change(binding()) is None
    assert remove_unused_import.is_default
    assert reexport_import.safety is FixSafety.REVIEW
    assert remove_unused_import.rule_callable == unused_import.callable_path


def test_fact_type_rejects_non_fact_annotations() -> None:
    with pytest.raises(TypeError, match="must be a Fact type"):
        fact_type(str)


def test_collection_literals_are_isolated_between_model_instances() -> None:
    first = ChecklistItem(name="first")
    second = ChecklistItem(name="second")
    assert first.checks == second.checks == {}
    assert first.checks is not second.checks

    span = SourceSpan(path="example.py")
    first_symbol = SymbolRef(id="first", name="first", declaration=NodeRef(id="a", span=span))
    second_symbol = SymbolRef(id="second", name="second", declaration=NodeRef(id="b", span=span))
    assert first_symbol.references == second_symbol.references == []
    assert first_symbol.references is not second_symbol.references
