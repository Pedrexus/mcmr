from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcmr.facts import ClassFact, OverrideFact, SymbolReachFact

from ..oracle import (
    MeasureReader,
    PylintMagnitudeOracle,
    Relation,
    Report,
    Site,
    Trees,
    differ,
    needs,
    needs_kernel,
    written,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [needs_kernel, needs("pylint")]

_PUBLIC_METHODS = PylintMagnitudeOracle(
    rules=("too-many-public-methods",), options=("--max-public-methods=0",)
)
_INSTANCE_ATTRIBUTES = PylintMagnitudeOracle(
    rules=("too-many-instance-attributes",), options=("--max-attributes=0",)
)
_ANCESTORS = PylintMagnitudeOracle(rules=("too-many-ancestors",), options=("--max-parents=0",))

_SURFACE = MeasureReader(rule_id="ALL-CLAS0003", family=ClassFact)
_FIELDS = MeasureReader(rule_id="ALL-CLAS0004", family=SymbolReachFact)
_ANCESTRY = MeasureReader(rule_id="ALL-CLAS0005", family=OverrideFact)


@pytest.fixture(scope="module")
def trees(tmp_path_factory: pytest.TempPathFactory) -> Trees:
    """Hand every drawn example a tree of its own, since a reading is cached by the tree."""
    return Trees(root=tmp_path_factory.mktemp("measures"))


def class_with_methods(name: str, public: int, *, hidden: int) -> str:
    """Return one class declaring the requested public methods beside members Pylint excludes."""
    return "\n".join(
        [
            f"class {name}:",
            "    def __init__(self):",
            "        self.value = 0",
            "",
            "    def __repr__(self):",
            '        return ""',
            "",
            *(f"    def open{index}(self):\n        return {index}\n" for index in range(public)),
            *(f"    def _step{index}(self):\n        return {index}\n" for index in range(hidden)),
        ]
    )


def class_with_attributes(name: str, count: int) -> str:
    """Return one class whose whole state is assigned to the receiver in its initializer."""
    body = [f"        self.field{index} = {index}" for index in range(count)] or ["        pass"]
    return "\n".join([f"class {name}:", "    def __init__(self):", *body, ""])


def measured(sites: Mapping[str, tuple[int, int]]) -> Report:
    """Return what a drawn corpus says about itself, one site per unit at each module's class."""
    return Report(
        reader="the strategy",
        sites=[
            Site.at(path, line)
            for path, (line, magnitude) in sites.items()
            for _ in range(magnitude)
        ],
    )


@st.composite
def surfaces(draw: st.DrawFn) -> dict[str, tuple[int, int]]:
    """Draw a handful of one-class modules, each stating how wide its surface is."""
    count = draw(st.integers(min_value=1, max_value=4))
    return {
        f"m{index}": (
            draw(st.integers(min_value=0, max_value=6)),
            draw(st.integers(min_value=0, max_value=3)),
        )
        for index in range(count)
    }


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(surfaces())
def test_public_method_count_agrees_with_pylint(
    trees: Trees, drawn: Mapping[str, tuple[int, int]]
) -> None:
    """MCMR answers `too-many-public-methods`, so it owes Pylint's exact magnitude.

    One class per module makes the module-scoped measurement and Pylint's class-scoped one the same
    number, so the comparison is an equality of magnitudes rather than an aggregate that could hide
    a disagreement inside a file. The strategy states each surface as it writes it and is held to
    Pylint for it too, so a generator that stopped meaning what it says fails here first.
    """
    root = trees.grow(
        {
            f"{name}.py": class_with_methods("Surface", public, hidden=hidden)
            for name, (public, hidden) in drawn.items()
        }
    )
    oracle = _PUBLIC_METHODS.report(root)
    stated = measured({f"{name}.py": (1, public) for name, (public, _) in drawn.items()})

    differ(
        stated, Relation.EQUALS, oracle, because="each module declares the surface it was drawn"
    )
    differ(
        _SURFACE.report(root),
        Relation.EQUALS,
        oracle,
        because="a public method is a declaration neither reader can count differently",
    )


def test_public_method_count_ignores_the_member_pylint_synthesizes_on_an_enum(
    tmp_path: Path,
) -> None:
    """An enum declaring nothing measures one for Pylint and zero here, which is the honest answer.

    Pylint's parser rewrites an enum class and gives it a `name` member the source never wrote, so
    every enumeration in a repository reads as having one public method. MCMR counts declarations,
    so the relation on an enum is that one synthesized member and nothing else, which is written
    into the comparison rather than left as a containment. Across MCMR's own source and GE4M this
    accounts for every difference between the two readers.
    """
    root = written(
        tmp_path,
        {
            "kinds.py": """from enum import StrEnum, auto


class Kind(StrEnum):
    FIRST = auto()
"""
        },
    )
    oracle = _PUBLIC_METHODS.report(root)

    assert oracle.states(Site.at("kinds.py", 4))
    differ(
        _SURFACE.report(root),
        Relation.EQUALS,
        oracle.minus(Site.at("kinds.py", 4)),
        because="Pylint's parser synthesizes a `name` member the enum source never wrote",
    )


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(st.integers(min_value=0, max_value=6), min_size=1, max_size=4))
def test_declared_field_count_agrees_with_pylint_on_receiver_state(
    trees: Trees, widths: Sequence[int]
) -> None:
    """Where every field is assigned to the receiver, the two populations coincide exactly.

    Pylint counts what an initializer assigns to `self`. MCMR counts every resolved data member of
    the type, which is the same set when the class states nothing in its own body, so this corpus
    is where an equality is the honest assertion.
    """
    root = trees.grow(
        {
            f"m{index}.py": class_with_attributes("Record", width)
            for index, width in enumerate(widths)
        }
    )
    oracle = _INSTANCE_ATTRIBUTES.report(root)
    stated = measured({f"m{index}.py": (1, width) for index, width in enumerate(widths)})

    differ(stated, Relation.EQUALS, oracle, because="each module assigns the state it was drawn")
    differ(
        _FIELDS.report(root),
        Relation.EQUALS,
        oracle,
        because="a field assigned to the receiver is one both readers resolve to the same type",
    )


def test_declared_field_count_reads_state_a_class_body_declares(tmp_path: Path) -> None:
    """A field the class body states is invisible to Pylint and counted here, deliberately.

    Pylint reads `instance_attrs`, which its own parser fills from assignments to the receiver, so
    a dataclass, a Pydantic model, and a plain annotated class body all measure zero there. MCMR
    reads resolved declarations, so it sees the two annotated fields as well, and naming both of
    them keeps the relation an equality where a containment would have held even if MCMR had lost
    the third.
    """
    root = written(
        tmp_path,
        {
            "record.py": """class Record:
    host: str
    port: int

    def __init__(self):
        self.timeout = 0
"""
        },
    )
    oracle = _INSTANCE_ATTRIBUTES.report(root)

    assert oracle.states(Site.at("record.py", 1))
    differ(
        _FIELDS.report(root),
        Relation.EQUALS,
        oracle.plus(Site.at("record.py", 1), Site.at("record.py", 1)),
        because="Pylint reads assignments to the receiver and never a field the body annotates",
    )


@settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(min_value=1, max_value=6))
def test_ancestor_count_agrees_with_pylint_on_a_local_chain(trees: Trees, length: int) -> None:
    """A chain this repository declares end to end is one MCMR resolves end to end.

    Pylint counts every ancestor it can infer and never counts `object`. MCMR counts every distinct
    ancestor the resolved inheritance chain names, so on a hierarchy rooted at a class with no base
    at all the two agree exactly at every link of the chain.
    """
    chain = ["class C0:\n    value = 0\n"]
    chain += [f"class C{index}(C{index - 1}):\n    pass\n" for index in range(1, length + 1)]
    root = trees.grow({"hierarchy.py": "\n\n".join(chain)})
    oracle = _ANCESTORS.report(root)
    stated = Report(
        reader="the strategy",
        sites=[
            Site.at("hierarchy.py", 4 * index + 1)
            for index in range(1, length + 1)
            for _ in range(index)
        ],
    )

    differ(stated, Relation.EQUALS, oracle, because="each link adds one ancestor to the one above")
    differ(
        _ANCESTRY.report(root),
        Relation.EQUALS,
        oracle,
        because="every base of this chain is declared here, so both readers walk the whole of it",
    )


def test_ancestor_count_declines_a_chain_this_repository_does_not_declare(tmp_path: Path) -> None:
    """A class whose bases are all external has no inheritance link here, and says so by silence.

    The two readers reach a chain differently and neither bound holds in general. Pylint imports
    what a class derives from and keeps walking, so it counts ancestors inside installed packages
    and drops any base it fails to import. MCMR counts every base name the source states, resolved
    or not, and never the ancestors of a name it could not resolve. They agree exactly when the
    whole chain is declared in the repository being read, which is what the equality case asserts.
    Here the chain is not: `Root` derives only `abc.ABC`, so no inheritance link exists for it and
    the rule reports nothing rather than guessing, while `Leaf` still measures both names above it.
    """
    root = written(
        tmp_path,
        {
            "sealed.py": """from abc import ABC


class Root(ABC):
    pass


class Leaf(Root):
    pass
"""
        },
    )
    oracle = _ANCESTORS.report(root)

    assert oracle.states(Site.at("sealed.py", 4), Site.at("sealed.py", 8), Site.at("sealed.py", 8))
    differ(
        _ANCESTRY.report(root),
        Relation.EQUALS,
        oracle.minus(Site.at("sealed.py", 4)),
        because="`Root` derives only `abc.ABC`, which this repository never declares",
    )
