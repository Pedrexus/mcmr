import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mcmr.rulebook.catalog import Catalog, RuleDefinition
from mcmr.rulebook.discovery import RuleModuleDiscovery

if TYPE_CHECKING:
    from collections.abc import Sequence

_SOURCE = Path(__file__).parents[2] / "src" / "rules"

# A rule page presents its measure, evidence, exceptions, examples, and sources in reading order.

# A docstring stating them differently would render as a different page.
_ORDER = ["Definition", "Evidence", "Exceptions", "Examples", "References"]

# The sections this suite owns. `References` is a machine-readable grammar `mcmr.upstream` parses
# and `tests/oracle_upstream/test_upstream_coverage.py` holds it to that, so it is
# read here only for its heading.
_OWNED = ("definition", "evidence", "exceptions", "examples")

# Long enough that a fragment fails and short enough that a genuinely small rule is not padded.
_FLOOR = 8

# The summary is one line of a website card, so it has to fit on one and end like a sentence.
_SUMMARY_CEILING = 99

# A word a docstring uses to say the shape it just described is the one that does not fire. An
# example naming one outcome and one of these has shown a reader both sides of the rule.
_QUIET = re.compile(
    r"(?i)\b(not|never|none|no|nothing|nobody|accepted|passes|pass|remains?|remain|excluded|"
    r"exempt|left alone|stays?|stay|unreported|abstains?|skipped)\b|`0`|`0\.0`|`false`"
)

_NUMBER = re.compile(r"`(\d+(?:\.\d+)?)`")
_BOOLEAN = re.compile(r"`(true|false)`")
_SETTING_SHAPED = re.compile(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`")
_RULE_REFERENCE = re.compile(r"\b((?:ALL|PY|RS|TS|CPP|CU)-[A-Z]{4}\d{4})\b")
_DOCSTRING = re.compile(r'(?ms)^    """.*?"""')

# A snake_case name in backticks that is neither a setting nor a local module name belongs
# somewhere else, so its reason must be stated.

# The table catches rules documenting knobs nobody implemented. `PY-FUNC0007` once shipped a
# predicate no frontend satisfied.

# `ancestor_depth` was also a field no frontend wrote. A documented name without an implementation
# is therefore a defect this catalog has produced twice.
_FOREIGN_NAMES: dict[str, str] = {
    "api_key": "a credential name the secrets rule matches, not a knob",
    "cached_property": "the `functools` decorator the caching rules point at",
    "create_model": "the Pydantic entry point the model foundation rule excludes",
    "ensure_future": "the `asyncio` entry point the task group rule resolves",
    "field_validator": "the Pydantic decorator the constraint rule inspects",
    "from_attributes": "a Pydantic validation option the redundant validate rule excludes",
    "from_table": "an example factory method in the Pydantic docstrings",
    "from_text": "an example class method in the descriptor docstring",
    "is_class": "an example wrapper name in the transparent wrapper docstring",
    "json_backend": "the registry key the example class derives from its own name",
    "load_profile": "an example function name in the effect visibility docstring",
    "loop_factory": "the `asyncio.Runner` argument that replaced the policy API",
    "model_config": "the Pydantic attribute a model foundation states its policy in",
    "model_dump": "the Pydantic serializer the projection rules point at",
    "model_post_init": "the Pydantic lifecycle hook several rules exempt",
    "model_validate": "the Pydantic entry point the redundant validate rule reports",
    "password_file": "a location name the secrets rule deliberately leaves alone",
    "publish_report": "an example function name in the abstraction level docstring",
    "return_exceptions": "the `asyncio.gather` argument the task group rule reads",
    "save_profile": "an example function name in the effect visibility docstring",
    "tmp_path": "the modern pytest fixture the legacy fixture rule points at",
    "tmp_path_factory": "the modern pytest fixture the legacy fixture rule points at",
    "to_owned": "the Rust method the ownership rules count beside `clone`",
    "token_env": "a location name the secrets rule deliberately leaves alone",
    "typing_extensions": "the backport module the prohibited type rule resolves through",
}


@pytest.fixture(scope="module")
def definitions() -> list[RuleDefinition]:
    """Return every rule the catalog builds, which is what a rule page is generated from."""
    return Catalog(modules=RuleModuleDiscovery().modules).definitions


def raw(definition: RuleDefinition) -> str:
    """Return the docstring of one rule exactly as its module states it."""
    module, _, qualname = definition.callable.rpartition(".")
    source = (_SOURCE / f"{module.replace('.', '/')}.py").read_text()
    body = next(
        candidate.group()
        for candidate in _DOCSTRING.finditer(source)
        if re.search(r"(?m)^\s*References\n\s*-+\n", candidate.group())
    )
    assert qualname in source
    return body


def prose(definition: RuleDefinition) -> str:
    """Return the documentation with its code spans, code blocks, and directives removed.

    What is left is the text a reader reads as English, which is the only text the punctuation
    rules apply to. A colon inside `.. code-block:: python` and a semicolon inside a Rust example
    are the language rather than the writing.
    """
    documentation = definition.documentation
    text = "\n".join(
        (documentation.summary, documentation.definition, documentation.evidence)
        + (documentation.exceptions, documentation.examples)
    )
    text = re.sub(r"(?ms)^ *\.\. (code-block|rubric):: ?.*?$", "", text)
    kept = [
        block
        for block in re.split(r"\n\n", text)
        if not all(line.startswith("   ") or not line.strip() for line in block.splitlines())
    ]
    return re.sub(
        r"`[^`]*`",
        "",
        "\n\n".join(kept),
        flags=re.S,
    )


def sections(definition: RuleDefinition) -> dict[str, str]:
    """Return the four sections this suite owns, keyed by their heading."""
    documentation = definition.documentation
    return {
        "Definition": documentation.definition,
        "Evidence": documentation.evidence,
        "Exceptions": documentation.exceptions,
        "Examples": documentation.examples,
    }


def test_every_rule_states_every_section_in_the_page_order(
    definitions: Sequence[RuleDefinition],
) -> None:
    """A rule page is generated from these five headings, so all five have to be there.

    The order is checked against the raw docstring rather than against the parsed sections,
    because the parser sorts what it finds and would hide a docstring that states Examples before
    Evidence.
    """
    stated = {
        definition.id: re.findall(r"(?m)^[ \t]*(\w+)\n[ \t]*-{3,}[ \t]*$", raw(definition))
        for definition in definitions
    }

    assert {rule: found for rule, found in stated.items() if found != _ORDER} == {}


def test_every_summary_reads_as_one_sentence(definitions: Sequence[RuleDefinition]) -> None:
    """The summary is the one line a reader sees before deciding to open the rule at all."""
    broken = {
        definition.id: definition.documentation.summary
        for definition in definitions
        if "\n" in definition.documentation.summary
        or not definition.documentation.summary
        or not definition.documentation.summary[0].isupper()
        or definition.documentation.summary[-1] not in ".!?"
        or len(definition.documentation.summary) > _SUMMARY_CEILING
    }

    assert broken == {}


def test_no_section_is_short_enough_to_read_as_a_fragment(
    definitions: Sequence[RuleDefinition],
) -> None:
    """A heading with a clause under it documents nothing, and reads as documented."""
    thin = {
        f"{definition.id} {heading}": len(text.split())
        for definition in definitions
        for heading, text in sections(definition).items()
        if len(text.split()) < _FLOOR
    }

    assert thin == {}


def test_every_example_anchors_on_code_rather_than_on_prose(
    definitions: Sequence[RuleDefinition],
) -> None:
    """An example that restates the definition in prose is not an example.

    The anchor is a code block or an inline literal, which is the difference between telling a
    reader what the rule is about and showing them the shape that fires.
    """
    unanchored = {
        definition.id: definition.documentation.examples
        for definition in definitions
        if ".. code-block::" not in definition.documentation.examples
        and not re.search(r"`[^`]+`", definition.documentation.examples)
    }

    assert unanchored == {}


def test_every_example_shows_both_a_case_that_fires_and_one_that_does_not(
    definitions: Sequence[RuleDefinition],
) -> None:
    """One shape alone leaves a reader unable to tell where the rule stops.

    A `Bad` and `Good` pair states both outright. Otherwise the section has to name two distinct
    results, which is two numbers for a measure, both Booleans for an occurrence, or two of the
    categories a closed category rule returns, or else say in words that the second shape stays
    quiet.
    """

    def contrasts(definition: RuleDefinition) -> bool:
        examples = definition.documentation.examples
        paired = re.search(r"(?m)^Bad\b", examples) and re.search(r"(?m)^Good\b", examples)
        named = {category for category in definition.categories if f"`{category}`" in examples}
        return bool(
            paired
            or len(set(_NUMBER.findall(examples))) >= 2
            or len(set(_BOOLEAN.findall(examples))) >= 2
            or len(named) >= 2
            or _QUIET.search(examples)
        )

    single = [definition.id for definition in definitions if not contrasts(definition)]

    assert single == []


def test_every_measure_says_what_its_number_is(definitions: Sequence[RuleDefinition]) -> None:
    """A count nobody explained is a number a reader has to reverse engineer from the body."""
    silent = {
        definition.id: definition.documentation.evidence
        for definition in definitions
        if definition.output in {"int", "float"}
        and not re.search(r"(?i)\bvalue\b", definition.documentation.evidence)
    }

    assert silent == {}


def test_the_prose_follows_the_house_punctuation(definitions: Sequence[RuleDefinition]) -> None:
    """No em dash, no colon, and no semicolon outside code, since the house style forbids them."""
    offending = {
        definition.id: character
        for definition in definitions
        for character in "—–:;"
        if character in prose(definition)
    }

    assert offending == {}


def test_inline_literals_are_spelled_with_one_backtick(
    definitions: Sequence[RuleDefinition],
) -> None:
    """One catalog spelling its own literals two ways renders as two different sites."""
    doubled = {
        f"{definition.id} {heading}": text
        for definition in definitions
        for heading, text in (
            {"Summary": definition.documentation.summary} | sections(definition)
        ).items()
        if "``" in text
    }

    assert doubled == {}


def test_every_setting_a_rule_declares_is_documented(
    definitions: Sequence[RuleDefinition],
) -> None:
    """A knob nobody wrote about is a knob nobody can use, and it is invisible in the catalog."""
    undocumented = {
        definition.id: [
            setting
            for setting in definition.settings
            if not re.search(
                rf"\b{setting}\b",
                "\n".join(sections(definition).values()),
            )
        ]
        for definition in definitions
        if any(
            not re.search(
                rf"\b{setting}\b",
                "\n".join(sections(definition).values()),
            )
            for setting in definition.settings
        )
    }

    assert undocumented == {}


def test_no_rule_documents_a_setting_its_module_never_states(
    definitions: Sequence[RuleDefinition],
) -> None:
    """A documented knob with nothing behind it promises behavior the rule does not have.

    Every backticked snake_case name has to be a setting the signature declares, a category the
    rule returns, a name the module states outside its docstring, or an entry in `FOREIGN_NAMES`
    with the reason it belongs to somebody else.
    """
    invented: dict[str, list[str]] = {}
    for definition in definitions:
        module = definition.callable.rpartition(".")[0].replace(".", "/")
        code = _DOCSTRING.sub("", (_SOURCE / f"{module}.py").read_text())
        known = {*definition.settings, *definition.categories, *_FOREIGN_NAMES}
        unknown = sorted(
            {
                name
                for name in _SETTING_SHAPED.findall("\n".join(sections(definition).values()))
                if name not in known and not re.search(rf"\b{name}\b", code)
            }
        )
        if unknown:
            invented[definition.id] = unknown

    assert invented == {}


def test_every_foreign_name_is_one_a_rule_actually_writes(
    definitions: Sequence[RuleDefinition],
) -> None:
    """The table cannot outlive the name it excuses, and every entry has to say why.

    Without this the exception table only grows, and an entry left behind after a docstring stops
    naming it is exactly the stale allowance a reader would trust.
    """
    written = {
        name
        for definition in definitions
        for name in _SETTING_SHAPED.findall("\n".join(sections(definition).values()))
        if name not in definition.settings and name not in definition.categories
    }

    assert set(_FOREIGN_NAMES) <= written
    assert all(reason for reason in _FOREIGN_NAMES.values())


def test_every_rule_a_docstring_names_is_one_this_catalog_declares(
    definitions: Sequence[RuleDefinition],
) -> None:
    """A cross reference to a rule that does not exist sends a reader nowhere."""
    known = {definition.id for definition in definitions}
    dangling = {
        definition.id: sorted(
            named
            for named in set(_RULE_REFERENCE.findall("\n".join(sections(definition).values())))
            if named not in known
        )
        for definition in definitions
    }

    assert {rule: missing for rule, missing in dangling.items() if missing} == {}
