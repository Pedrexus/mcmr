import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mcmr.accounting.upstream import ReferenceParser
from mcmr.domain.contracts import RuleDefinition
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

_PACKAGE = Path(__file__).parents[2]
_SOURCE = _PACKAGE / "src" / "rules"
_SYSTEM = _PACKAGE / "SYSTEM.md"

# The order a rule page reads in. A reader meets what is measured, what is recorded, where the rule
# deliberately stays quiet, what that looks like in code, and only then where it came from.
_ORDER = ["Definition", "Evidence", "Exceptions", "Examples", "References"]

# Every docstring in a rule module, so a rule with a fix beside it is read as two.
_DOCSTRING = re.compile(r'(?ms)^    """.*?"""')


def underline(width: int) -> str:
    """Return the reStructuredText rule a heading of one width needs beneath it."""
    return "".ljust(width, "-")


def body(headings: Sequence[str], width: int = 0) -> str:
    """Return a docstring stating one line under each heading, the rules sized to the headings."""
    written = "".join(
        f"\n    {name}\n    {underline(width or len(name))}\n    text\n" for name in headings
    )
    return f'    """Summary.\n{written}    """'


def fragment(name: str) -> str:
    """Return the template fragment for one section, its underline sized to its own heading."""
    text = rf"(?P<{name.casefold()}>(?:    [^\n]*\S\n|\n)*?)"
    return rf"\n    {name}\n    {underline(len(name))}\n{text}"


# The whole rule docstring is one expression. A generator reads a page from it, and the catalog
# check keeps the page and source aligned.

# Closing quotes stand alone because a References section may end in a quoted title. Matching a
# line ending in `"` against `"""` would not parse as Python.
_TEMPLATE = re.compile(
    r'    """(?P<summary>\S[^\n]*)\n' + "".join(fragment(name) for name in _ORDER) + r'    """'
)


@pytest.fixture(scope="module")
def definitions() -> list[RuleDefinition]:
    """Return every rule the catalog builds, which is what a rule page is generated from."""
    return Catalog(modules=RuleModuleDiscovery().modules).definitions


@pytest.fixture(scope="module")
def docstrings(definitions: Sequence[RuleDefinition]) -> dict[str, str]:
    """Return the documenting docstring of every rule, exactly as its module states it."""
    found: dict[str, str] = {}
    for definition in definitions:
        module = definition.callable.rpartition(".")[0].replace(".", "/")
        source = (_SOURCE / f"{module}.py").read_text()
        found[definition.id] = next(
            candidate.group()
            for candidate in _DOCSTRING.finditer(source)
            if re.search(r"(?m)^\s*References\n\s*-+\n", candidate.group())
        )
    return found


def test_every_rule_docstring_matches_the_template(docstrings: Mapping[str, str]) -> None:
    """One expression reads a whole rule page, so the template cannot drift from the catalog.

    The alternative is a description of the shape kept beside the parser, which is the arrangement
    the References grammar already outgrew. A docstring that misses a section, states them in
    another order, sizes an underline to something other than its heading, or closes its quotes on
    the last line of prose fails here rather than rendering as a page nobody meant to publish.
    """
    off = sorted(rule for rule, stated in docstrings.items() if not _TEMPLATE.fullmatch(stated))

    assert len(docstrings) == 275
    assert off == []


def test_every_docstring_opens_on_a_summary_and_closes_on_its_own_line(
    docstrings: Mapping[str, str],
) -> None:
    """The summary is the card a site renders, and the last line is what lets a title be quoted."""
    summaries = [_TEMPLATE.fullmatch(stated) for stated in docstrings.values()]

    assert all(
        match is not None and match["summary"].endswith((".", "!", "?")) for match in summaries
    )
    assert all(stated.endswith('\n    """') for stated in docstrings.values())


@pytest.mark.parametrize(
    ("name", "headings", "width"),
    [
        ("a missing section", _ORDER[:4], 0),
        ("the sections out of order", (_ORDER[0], _ORDER[3], _ORDER[1], _ORDER[2], _ORDER[4]), 0),
        ("an underline shorter than its heading", _ORDER, 3),
    ],
)
def test_a_docstring_off_the_template_is_refused(
    name: str, headings: Sequence[str], width: int
) -> None:
    """A template nothing fails is a template nothing is held to, so the misses are exercised."""
    assert _TEMPLATE.fullmatch(body(headings, width)) is None, name


def test_the_closing_quotes_may_not_share_a_line_with_the_last_reference() -> None:
    """A title ends in a quote, and one written against the closing quotes will not parse."""
    written = body(_ORDER)
    inline = written.rstrip()[: -len('"""')].rstrip() + '"""'

    assert _TEMPLATE.fullmatch(written) is not None
    assert _TEMPLATE.fullmatch(inline) is None


def test_the_documented_grammar_is_the_one_the_parser_runs() -> None:
    """A documented grammar and an implemented one are two grammars the day they disagree.

    `SYSTEM.md` prints the expression across three lines so a reader can see the three shapes a
    line may take. Joining them back has to give the parser's own pattern character for character,
    which is what stops the document from describing a grammar the catalog was never held to.
    """
    blocks = re.findall(r"(?ms)^```\w*\n(.*?)^```\n", _SYSTEM.read_text())
    documented = next(block for block in blocks if "(?P<url>" in block)

    assert documented.replace("\n", "") == ReferenceParser.grammar.pattern


def test_the_documented_template_states_the_sections_in_the_page_order() -> None:
    """The template a reader follows and the template the catalog is held to are one template."""
    blocks = re.findall(r"(?ms)^```\w*\n(.*?)^```\n", _SYSTEM.read_text())
    documented = next(block for block in blocks if "{summary}" in block)

    assert re.findall(r"(?m)^    (\w+)$", documented) == _ORDER
    assert all(f"\n    {underline(len(name))}\n" in documented for name in _ORDER)
    assert documented.endswith('    """\n')


def test_every_line_of_every_references_section_is_one_line_of_the_grammar(
    definitions: Sequence[RuleDefinition],
) -> None:
    """The References grammar is the regular expression the parser runs, not a paraphrase of it.

    Reading it straight off `ReferenceParser` is the point. A section documented one way and parsed
    another is how the literature half became prose nobody could count in the first place.
    """
    off = [
        (definition.id, line)
        for definition in definitions
        for line in definition.documentation.references
        if ReferenceParser.grammar.fullmatch(line) is None
    ]

    assert off == []
