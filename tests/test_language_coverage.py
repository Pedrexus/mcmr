from typing import TYPE_CHECKING

import pytest

from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.facts import CommentFact, SyntaxFact
from mcmr.kernel import Kernel, buildable
from mcmr.models import RuleLane, RuleScope
from mcmr.rules.general.deterministic.comments.r0006 import unresolved_work_marker
from mcmr.rules.general.deterministic.naming.r0001 import uninformative_local_name
from mcmr.upstream import ClaimIndex, ToolRegistry
from tests.conftest import BINARY, needs_kernel

if TYPE_CHECKING:
    from pathlib import Path

# One fixture per language, each stating the same program so a family that answers for one and not
# for another is a gap in the frontend rather than a difference between the fixtures. Every one
# holds a work marker, a run of commented-out source, a sentence that is only prose, a type with a
# method, a branch, a call, and a local named too briefly to say what it holds.
#
# Each also derives its type from a base declaring the same method, and reaches its own call
# through a receiver rather than by a bare name. Neither was here before, and the two absences cost
# the same thing: a family the reference frontend never answered for the fixture could not be
# compared at all, so `OverrideFact` sat outside the guard while eleven general rules read it
# empty, and a call name nobody compared let a frontend drop the receiver and turn every rule that
# matches a builtin by name into a false positive.
FIXTURES: dict[str, tuple[str, str]] = {
    "python": (
        "sample.py",
        "import json\n\n\nclass Base:\n"
        "    def load(self, name: str) -> str:\n"
        "        return ''\n\n\n"
        "# TODO: handle the empty case\nclass Loader(Base):\n"
        '    """Load one record."""\n\n'
        "    def load(self, name: str) -> str:\n"
        "        # d = read(name)\n"
        "        # e = parse(d)\n"
        "\n"
        "        # retry twice before giving up\n"
        "        d = json.dumps({'name': name})\n"
        "        if name:\n"
        "            return d\n"
        "        return ''\n",
    ),
    "rust": (
        "sample.rs",
        "use std::fmt::Debug;\n\npub trait Base {\n"
        "    fn load(&self, name: &str) -> usize;\n}\n\n"
        "// TODO: handle the empty case\npub struct Loader {\n"
        "    limit: usize,\n}\n\nimpl Base for Loader {\n"
        "    fn load(&self, name: &str) -> usize {\n"
        "        // let d = read(name);\n"
        "        // let e = parse(d);\n"
        "\n"
        "        // retry twice before giving up\n"
        "        let d = name.len();\n"
        "        if d > self.limit { return self.limit; }\n"
        "        d\n"
        '    }\n}\n\npub fn describe(value: &impl Debug) -> String { format!("{value:?}") }\n',
    ),
    "typescript": (
        "sample.ts",
        'import { readFile } from "node:fs";\n\n'
        "export class Base {\n  load(name: string): number {\n    return 0;\n  }\n}\n\n"
        "// TODO: handle the empty case\n"
        "export class Loader extends Base {\n"
        "  load(name: string): number {\n"
        "    // const d = read(name);\n"
        "    // const e = parse(d);\n"
        "\n"
        "    // retry twice before giving up\n"
        "    const d = name.length;\n"
        "    if (d > 0) {\n      return d;\n    }\n"
        "    return name.trim().length;\n"
        "  }\n}\n",
    ),
    "c": (
        "sample.c",
        "#include <string.h>\n\n/* TODO: handle the empty case */\nstruct Loader {\n"
        "  int limit;\n  int (*read)(const char* name);\n};\n\n"
        "int load(struct Loader* self, const char* name) {\n"
        "  // int d = read(name);\n"
        "  // int e = parse(d);\n"
        "\n"
        "  // retry twice before giving up\n"
        "  int d = self->read(name);\n"
        "  if (d > self->limit) {\n    return self->limit;\n  }\n"
        "  return d;\n}\n",
    ),
    "cpp": (
        "sample.cpp",
        "#include <string>\n\nclass Base {\n public:\n"
        "  int load(const std::string& name) { return 0; }\n};\n\n"
        "// TODO: handle the empty case\nclass Loader : public Base {\n public:\n"
        "  int load(const std::string& name) {\n"
        "    // int d = read(name);\n"
        "    // int e = parse(d);\n"
        "\n"
        "    // retry twice before giving up\n"
        "    int d = name.size();\n"
        "    if (d > limit) {\n      return limit;\n    }\n"
        "    return d;\n  }\n private:\n  int limit;\n};\n",
    ),
    "cuda": (
        "sample.cu",
        "#include <cuda_runtime.h>\n\nclass Base {\n public:\n"
        "  int load(const Reader& source) { return 0; }\n};\n\n"
        "// TODO: handle the empty case\nclass Loader : public Base {\n public:\n"
        "  int load(const Reader& source) {\n"
        "    // int d = read(source);\n"
        "    // int e = parse(d);\n"
        "\n"
        "    // retry twice before giving up\n"
        "    int d = source.size();\n"
        "    if (d > limit) {\n      return limit;\n    }\n"
        "    return d;\n  }\n private:\n  int limit;\n};\n\n"
        "__global__ void scale(float* data) { data[0] = data[0] * 2.0f; }\n",
    ),
}

# The one member call every fixture makes, as its own language spells the receiver. A general rule
# reading a tree matches a builtin by its bare name, so a frontend that hands back `size` where the
# source wrote `name.size()` makes every such rule answer for any value holding a method of that
# name. The receiver has to survive, and comparing the whole name is what proves it did.
RECEIVER_CALLS: dict[str, str] = {
    "python": "json.dumps",
    "rust": "name.len",
    "typescript": "name.trim",
    "c": "self.read",
    "cpp": "name.size",
    "cuda": "source.size",
}

SUFFIXES: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "rust": (".rs",),
    "typescript": (".ts",),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".hpp"),
    "cuda": (".cu", ".cuh"),
}

# The families whose evidence is the repository rather than one file's source. No frontend was
# ever meant to fill one, so a language that answers it differently is stating something about the
# fixture rather than about the frontend, and the coverage comparison leaves them out.
REPOSITORY_WIDE = frozenset(
    {
        "CloneGroupFact",
        "DependencyComponentFact",
        "InteropFact",
        "ProjectConfigurationFact",
        "RepositoryHistoryFact",
        "RouteFact",
    }
)

# Every family a general rule reads that the reference frontend answers, and the languages that do
# not answer it, each with the reason it cannot yet. This is the ledger the coverage test holds the
# kernel to. A general rule reading a family nobody outside Python fills reports zero everywhere
# else, which reads exactly like a clean repository and is worse than the rule not existing, so a
# gap has to be written down here or the test fails.
GAPS: dict[str, dict[str, str]] = {
    "AttributeAccessFact": {
        "rust": "no frontend but Python resolves an access to the declaration it reaches",
        "typescript": "the same, and the frontend never reaches the repository graph",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "BranchFact": {
        "rust": "the dispatch candidate the family carries is a Python match and if-chain shape",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "CallFact": {
        "typescript": "the frontend fills the four shared families and no others yet",
    },
    "CommentFact": {
        "typescript": "the frontend fills the four shared families and no others yet",
    },
    "OverrideFact": {
        "c": "the language states no inheritance, so no member ever meets one it replaces",
    },
    "LiteralGroupFact": {
        "rust": "repeated literals are grouped only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "MethodGroupFact": {
        "rust": "repeated method bodies are grouped only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "ParameterFact": {
        "rust": "the configuration-object shape is read only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "ProseSegmentFact": {
        "rust": "prose is read out of Python docstrings and no other frontend collects it",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "StringExpressionFact": {
        "rust": "string expressions are collected only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "WaiverFact": {
        "rust": "a waiver is read as a Python suppression comment and no other form yet",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
}


@pytest.fixture(scope="module")
def repositories(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Write one small repository per language, each stating the same program."""
    written = {}
    for language, (name, source) in FIXTURES.items():
        root = tmp_path_factory.mktemp(language)
        (root / name).write_text(source)
        written[language] = root
    return written


def general_families() -> set[str]:
    """Return every fact family a general deterministic rule reads and the kernel can build."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    buildables = buildable()
    return {
        definition.fact
        for definition in catalog.definitions
        if definition.scope is RuleScope.GENERAL
        and definition.lane == RuleLane.DETERMINISTIC
        and definition.fact in buildables
        and definition.fact not in REPOSITORY_WIDE
    }


def answered(root: Path, language: str, families: set[str]) -> set[str]:
    """Return the families the kernel actually filled for one language's repository."""
    types = buildable()
    kernel = Kernel(binary=BINARY, root=root, suffixes=SUFFIXES[language])
    workspace = kernel.build(sorted(families), {name: types[name] for name in families})
    return {family.__name__ for family, facts in workspace.streams.items() if facts}


@needs_kernel
@pytest.mark.parametrize("language", sorted(set(FIXTURES) - {"python"}))
def test_a_family_a_general_rule_reads_answers_for_every_language(
    language: str, repositories: dict[str, Path]
) -> None:
    """A family claiming to be language-neutral has to be filled by every frontend.

    Python is the reference frontend, so whatever it answers is what a general rule was written
    against. Any other language answering less is a rule that silently reports zero there, which a
    reader cannot tell apart from a clean repository. That is why a gap has to be written into
    `GAPS` with its reason rather than discovered later by somebody trusting the catalog.
    """
    families = general_families()
    reference = answered(repositories["python"], "python", families)
    declared = {family for family in reference if language not in GAPS.get(family, {})}

    assert answered(repositories[language], language, families) == declared


def test_every_declared_gap_names_a_family_a_general_rule_reads() -> None:
    """The ledger cannot outlive the gap it records, and cannot invent one either."""
    families = general_families()

    assert set(GAPS) <= families
    assert all(set(languages) <= set(FIXTURES) - {"python"} for languages in GAPS.values())
    assert all(reason for languages in GAPS.values() for reason in languages.values())


def test_every_general_tool_claim_has_a_provider_in_the_tools_languages() -> None:
    """A general rule cannot cover a tool where its fact family is absent.

    Tool profiles state the languages their inventories describe, and the frontend ledger states
    every family those languages still lack. Joining the two makes language support part of the
    coverage account instead of an assumption hidden behind an `ALL` identifier.
    """
    definitions = tuple(Catalog(modules=RuleModuleDiscovery().modules).definitions)
    profiles = ToolRegistry().by_name
    claims = ClaimIndex(definitions=definitions).claims
    wrong = {
        (claim.rule, claim.upstream.tool, language.value, claim.fact)
        for claim in claims
        if claim.scope is RuleScope.GENERAL
        for language in profiles[claim.upstream.tool.casefold()].languages
        if language.value in GAPS.get(claim.fact, {})
    }

    assert not wrong, sorted(wrong)


@needs_kernel
@pytest.mark.parametrize("language", sorted(FIXTURES))
def test_the_work_marker_rule_reads_every_language_the_comment_family_covers(
    language: str, repositories: dict[str, Path]
) -> None:
    """One rule, written once, finds the same marker in six languages.

    Each fixture states exactly one `TODO` at the top and nothing else a marker matches, so the
    expected answer is hand-computed rather than compared against a second reader.
    """
    if language in GAPS.get("CommentFact", {}):
        pytest.skip(f"no comment family for {language} yet")
    kernel = Kernel(binary=BINARY, root=repositories[language], suffixes=SUFFIXES[language])
    workspace = kernel.build(["CommentFact"], {"CommentFact": CommentFact})
    facts = workspace.stream(CommentFact)

    assert sum(unresolved_work_marker(fact) for fact in facts) == 1


@needs_kernel
@pytest.mark.parametrize("language", sorted(FIXTURES))
def test_commented_out_source_is_told_apart_from_prose_in_every_language(
    language: str, repositories: dict[str, Path]
) -> None:
    """Each fixture comments out two lines of its own body and writes one sentence beside them."""
    if language in GAPS.get("CommentFact", {}):
        pytest.skip(f"no comment family for {language} yet")
    kernel = Kernel(binary=BINARY, root=repositories[language], suffixes=SUFFIXES[language])
    groups = [
        group
        for fact in kernel.build(["CommentFact"], {"CommentFact": CommentFact}).stream(CommentFact)
        for group in fact.groups
    ]

    assert [group.line_count for group in groups if group.parses_as_source] == [2]
    assert any(not group.parses_as_source and group.line_count == 1 for group in groups)


@needs_kernel
@pytest.mark.parametrize("language", sorted(FIXTURES))
def test_the_naming_rule_reads_a_body_in_every_language_the_syntax_family_covers(
    language: str, repositories: dict[str, Path]
) -> None:
    """Each fixture binds exactly one local named `d`, which is the hand-computed answer."""
    if language in GAPS.get("SyntaxFact", {}):
        pytest.skip(f"no syntax family for {language} yet")
    kernel = Kernel(binary=BINARY, root=repositories[language], suffixes=SUFFIXES[language])
    facts = kernel.build(["SyntaxFact"], {"SyntaxFact": SyntaxFact}).stream(SyntaxFact)

    assert sum(uninformative_local_name(fact).value for fact in facts) == 1


@needs_kernel
def test_a_declaration_carries_the_same_shape_whichever_frontend_read_it(
    repositories: dict[str, Path],
) -> None:
    """The one method every fixture states arrives as a callable holding a branch and a call."""
    shapes = {}
    for language in sorted(set(FIXTURES) - set(GAPS.get("SyntaxFact", {}))):
        held = overriding(repositories[language], language)
        assert held.tree is not None
        shapes[language] = (
            held.kind,
            bool(held.tree.of_kind("branch")),
            bool(held.tree.of_kind("return")),
            held.tree.names("binding"),
        )

    assert set(shapes) == {"python", "rust", "typescript", "c", "cpp", "cuda"}
    assert all(shape == ("callable", True, True, ["d"]) for shape in shapes.values()), shapes


def overriding(root: Path, language: str) -> SyntaxFact:
    """Return the `load` each fixture writes over the one it inherits, never the base's own."""
    kernel = Kernel(binary=BINARY, root=root, suffixes=SUFFIXES[language])
    facts = kernel.build(["SyntaxFact"], {"SyntaxFact": SyntaxFact}).stream(SyntaxFact)
    named = [fact for fact in facts if fact.qualname.endswith("load")]
    return next((fact for fact in named if "Loader" in fact.qualname), named[0])


@needs_kernel
def test_a_call_through_a_receiver_keeps_the_receiver_in_every_language(
    repositories: dict[str, Path],
) -> None:
    """A rule matching a builtin by its bare name is unsound the moment a frontend drops one.

    `state.exec(...)` arriving as `exec` made a benchmark runner read as the scope builtin every
    language spells that way, and nothing here could see it, because the shape comparison read the
    names a body binds and never the names it calls. So the assertion is the whole name each
    frontend states rather than the family merely being non-empty.
    """
    read = {}
    for language in RECEIVER_CALLS:
        held = overriding(repositories[language], language).tree
        assert held is not None
        read[language] = held.names("call")

    assert read == {language: [name] for language, name in RECEIVER_CALLS.items()}


def test_every_language_answering_for_code_states_the_call_it_is_compared_on() -> None:
    """A language added to the fixtures cannot skip the comparison by not being listed."""
    assert set(RECEIVER_CALLS) == set(FIXTURES) - set(GAPS.get("SyntaxFact", {}))
