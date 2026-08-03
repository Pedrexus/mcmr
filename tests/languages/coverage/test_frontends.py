from typing import TYPE_CHECKING

import pytest

from mcmr.facts import CommentFact, SyntaxFact
from mcmr.kernel import Kernel
from mcmr.rules.general import uninformative_local_name, unresolved_work_marker
from mcmr.table import AnalysisSession

from ...support import kernel_binary, needs_kernel
from .support import (
    answered,
    gap_reasons,
    general_families,
    language_fixtures,
    language_suffixes,
    query_count,
    receiver_calls,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


@pytest.fixture(scope="module")
def repositories(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Write one small repository per language, each stating the same program."""
    written = {}
    for language, (name, source) in language_fixtures().items():
        root = tmp_path_factory.mktemp(language)
        (root / name).write_text(source)
        written[language] = root
    return written


@needs_kernel
@pytest.mark.parametrize("language", sorted(set(language_fixtures()) - {"python"}))
def test_a_family_a_general_rule_reads_answers_for_every_language(
    language: str, repositories: Mapping[str, Path]
) -> None:
    """A family claiming to be language-neutral has to be filled by every frontend.

    Python is the reference frontend, so whatever it answers is what a general rule was written
    against. Any other language answering less is a rule that silently reports zero there, which a
    reader cannot tell apart from a clean repository. That is why a gap has to be written into
    `GAPS` with its reason rather than discovered later by somebody trusting the catalog.
    """
    families = general_families()
    reference = answered(repositories["python"], "python", families)
    declared = {family for family in reference if language not in gap_reasons().get(family, {})}

    assert answered(repositories[language], language, families) == declared


@needs_kernel
@pytest.mark.parametrize("language", sorted(language_fixtures()))
def test_the_work_marker_rule_reads_every_language_the_comment_family_covers(
    language: str, repositories: Mapping[str, Path]
) -> None:
    """One rule, written once, finds the same marker in six languages.

    Each fixture states exactly one `TODO` at the top and nothing else a marker matches, so the
    expected answer is hand-computed rather than compared against a second reader.
    """
    if language in gap_reasons().get("CommentFact", {}):
        pytest.skip(f"no comment family for {language} yet")
    subject = AnalysisSession(
        repositories[language],
        suffixes=language_suffixes()[language],
        typed_families=[CommentFact.__name__],
    ).table(CommentFact)

    assert query_count(unresolved_work_marker, subject) == 1


@needs_kernel
@pytest.mark.parametrize("language", sorted(language_fixtures()))
def test_commented_out_source_is_told_apart_from_prose_in_every_language(
    language: str, repositories: Mapping[str, Path]
) -> None:
    """Each fixture comments out two lines of its own body and writes one sentence beside them."""
    if language in gap_reasons().get("CommentFact", {}):
        pytest.skip(f"no comment family for {language} yet")
    kernel = Kernel(
        binary=kernel_binary(), root=repositories[language], suffixes=language_suffixes()[language]
    )
    groups = [
        group
        for fact in kernel.build(["CommentFact"], {"CommentFact": CommentFact}).stream(CommentFact)
        for group in fact.groups
    ]

    assert [group.line_count for group in groups if group.parses_as_source] == [2]
    assert any(not group.parses_as_source and group.line_count == 1 for group in groups)


@needs_kernel
@pytest.mark.parametrize("language", sorted(language_fixtures()))
def test_the_naming_rule_reads_a_body_in_every_language_the_syntax_family_covers(
    language: str, repositories: Mapping[str, Path]
) -> None:
    """Each fixture binds exactly one local named `d`, which is the hand-computed answer."""
    if language in gap_reasons().get("SyntaxFact", {}):
        pytest.skip(f"no syntax family for {language} yet")
    subject = AnalysisSession(
        repositories[language],
        suffixes=language_suffixes()[language],
        typed_families=[SyntaxFact.__name__],
    ).syntax_tables()

    assert query_count(uninformative_local_name, subject) == 1


@needs_kernel
def test_a_declaration_carries_the_same_shape_whichever_frontend_read_it(
    repositories: Mapping[str, Path],
) -> None:
    """The one method every fixture states arrives as a callable holding a branch and a call."""
    shapes = {}
    for language in sorted(set(language_fixtures()) - set(gap_reasons().get("SyntaxFact", {}))):
        held = overriding(repositories[language], language)
        tree = held.root
        assert tree is not None
        shapes[language] = (
            held.kind,
            bool(tree.of_kind("branch")),
            bool(tree.of_kind("return")),
            tree.names("binding"),
        )

    assert set(shapes) == {"python", "rust", "typescript", "c", "cpp", "cuda"}
    assert all(shape == ("callable", True, True, ["d"]) for shape in shapes.values()), shapes


def overriding(root: Path, language: str) -> SyntaxFact:
    """Return the `load` each fixture writes over the one it inherits, never the base's own."""
    kernel = Kernel(binary=kernel_binary(), root=root, suffixes=language_suffixes()[language])
    facts = kernel.build(["SyntaxFact"], {"SyntaxFact": SyntaxFact}).stream(SyntaxFact)
    named = [fact for fact in facts if fact.qualname.endswith("load")]
    return next((fact for fact in named if "Loader" in fact.qualname), named[0])


@needs_kernel
def test_a_call_through_a_receiver_keeps_the_receiver_in_every_language(
    repositories: Mapping[str, Path],
) -> None:
    """A rule matching a builtin by its bare name is unsound the moment a frontend drops one.

    `state.exec(...)` arriving as `exec` made a benchmark runner read as the scope builtin every
    language spells that way, and nothing here could see it, because the shape comparison read the
    names a body binds and never the names it calls. So the assertion is the whole name each
    frontend states rather than the family merely being non-empty.
    """
    read = {}
    for language in receiver_calls():
        held = overriding(repositories[language], language).root
        assert held is not None
        read[language] = held.names("call")

    assert read == {language: [name] for language, name in receiver_calls().items()}


def test_every_language_answering_for_code_states_the_call_it_is_compared_on() -> None:
    """A language added to the fixtures cannot skip the comparison by not being listed."""
    assert set(receiver_calls()) == set(language_fixtures()) - set(
        gap_reasons().get("SyntaxFact", {})
    )
