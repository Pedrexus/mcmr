import os
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcmr.facts import (
    ImportBindingFact,
)

from ...oracle import (
    DeclarationReader,
    Oracle,
    Relation,
    Report,
    RuffOracle,
    Shape,
    Site,
    Source,
    Trees,
    assembled,
    differ,
    needs,
    needs_kernel,
    written,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mcmr.plugins import Fact


pytestmark = [needs_kernel, needs("pylint", "ruff")]

_GENERATED = "pkg/generated.py"

# Every shape Pylint, Ruff, and MCMR answer identically. The old narrow generator let a resolver
# miss `elif`, `except`, `__future__`, and wildcard import cases.

# Each entry names its module and callable so any subset still assembles into meaningful source.
_AGREED: list[Shape] = [
    Shape(opening=["import json"], body=["def read_call():", "    return json.dumps(1)"]),
    Shape(opening=["import math"], reported={0}),
    Shape(
        opening=["import re"],
        body=[
            "def read_elif(value):",
            "    if value == 1:",
            "        return 0",
            "    elif isinstance(value, re.Match):",
            "        return 1",
            "    return 2",
        ],
    ),
    Shape(
        opening=["import decimal"],
        body=[
            "def read_handler(value):",
            "    try:",
            "        return value",
            "    except decimal.DecimalException:",
            "        return None",
        ],
    ),
    Shape(
        opening=["import string"],
        body=[
            "def read_match(value):",
            "    match value:",
            "        case string.Template():",
            "            return 1",
            "    return 2",
        ],
    ),
    Shape(opening=["from textwrap import *"]),
    Shape(opening=["import calendar"], body=['__all__ = ["calendar"]']),
    Shape(
        opening=[
            "from typing import TYPE_CHECKING",
            "",
            "if TYPE_CHECKING:",
            "    from uuid import UUID",
        ],
        body=["def read_annotation(value: UUID) -> None:", "    return None"],
    ),
    Shape(
        opening=["from pathlib import Path"],
        body=['def read_string(value: "Path") -> None:', "    return None"],
    ),
    Shape(opening=["from fractions import Fraction"], body=["type Ratio = Fraction"]),
    Shape(opening=["import gettext as translator"], reported={0}),
    Shape(
        opening=["from statistics import mean as average"],
        body=["def read_alias(rows):", "    return average(rows)"],
    ),
    Shape(opening=["import os.path"], reported={0}),
    Shape(
        opening=["from . import sibling"],
        body=["def read_sibling():", "    return sibling.VALUE"],
    ),
    Shape(opening=["from .sibling import VALUE"], reported={0}),
]

_UNUSED_IMPORT = DeclarationReader(rule_id="PY-IMPO0003", family=ImportBindingFact)
_PYTHON_UNUSED_IMPORT = _UNUSED_IMPORT.model_copy(update={"languages": ["python"]})


@pytest.fixture(scope="module")
def trees(tmp_path_factory: pytest.TempPathFactory) -> Trees:
    """Hand every drawn example a tree of its own, since a reading is cached by the tree."""
    return Trees(root=tmp_path_factory.mktemp("unused"))


@st.composite
def program(draw: st.DrawFn) -> Source:
    """Build one module out of import shapes and state which of its lines stay reported.

    A `__future__` directive has to be the first statement a module makes, so it is drawn on its
    own and handed over as the prologue rather than sampled among the rest. Every other shape is
    independent of every other, which is what lets any subset of them be concatenated and still
    parse.
    """
    prologue = ["from __future__ import annotations"] if draw(st.booleans()) else []
    return draw(assembled(_AGREED, prologue=prologue))


def package(source: str) -> dict[str, str]:
    """Return the package one generated module needs, so a relative import has somewhere to go."""
    return {
        "pkg/__init__.py": "",
        "pkg/sibling.py": "VALUE = 1\n",
        _GENERATED: source,
    }


def expected(source: Source) -> Report:
    """Return what the drawn shapes say about themselves, as a reader of their own."""
    return Report(
        reader="the strategy",
        sites=[Site.at(_GENERATED, line) for line in source.reported],
    )


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(program())
def test_unused_import_agrees_with_pylint(trees: Trees, source: Source) -> None:
    """MCMR claims this message natively, so it owes Pylint's exact answer on any program.

    The lines are compared rather than the names, because Pylint spells the name it reports four
    different ways depending on the import that bound it and the last word of `Unused VALUE
    imported from sibling` is the module rather than the binding. A line is what both readers agree
    they are pointing at, and the path is the one relative to the tree, so a package holding three
    files stays three files.
    """
    root = trees.grow(package(source.text))
    oracle = Oracle.of("pylint", "unused-import").report(root)

    differ(expected(source), Relation.EQUALS, oracle, because="each shape states its own answer")
    differ(
        _UNUSED_IMPORT.report(root),
        Relation.EQUALS,
        oracle,
        because="MCMR claims `unused-import` natively, so it owes Pylint's exact answer",
    )


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(program())
def test_unused_import_agrees_with_ruff_on_the_same_programs(trees: Trees, source: Source) -> None:
    """Two oracles reading the same generated modules, since neither one reads every shape.

    Pylint and Ruff disagree about several ordinary imports, so a generator wide enough to be worth
    having cannot be held to both on every shape it produces. `AGREED` is the subset all three
    answer identically, and asking Ruff for it as well is what keeps the subset honest instead of
    leaving it a claim about Pylint alone.
    """
    root = trees.grow(package(source.text))
    oracle = Oracle.of("ruff", "F401").report(root)

    differ(expected(source), Relation.EQUALS, oracle, because="each shape states its own answer")
    differ(
        _PYTHON_UNUSED_IMPORT.report(root),
        Relation.EQUALS,
        oracle,
        because="Ruff cannot open anything but Python, so only the Python facts are compared",
    )


@pytest.mark.parametrize(
    ("name", "source", "expected"),
    [
        (
            "probe",
            """def run():
    try:
        import h2
    except ImportError:
        raise ImportError("install the extra") from None
    return 1
""",
            {"mcmr": [], "ruff": [3], "pylint": []},
        ),
        (
            "redundant_alias",
            "import json as json\n",
            {"mcmr": [], "ruff": [], "pylint": [1]},
        ),
        (
            "augmented_all",
            'import json\n\n__all__ = []\n__all__ += ["json"]\n',
            {"mcmr": [], "ruff": [], "pylint": [1]},
        ),
        (
            "aliased_forward",
            'from decimal import Decimal\n\ntype Money = "Decimal"\n',
            {"mcmr": [], "ruff": [], "pylint": [1]},
        ),
        (
            "type_only",
            """from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from numbers import Number
""",
            {"mcmr": [4], "ruff": [4], "pylint": []},
        ),
    ],
)
def test_unused_import_reads_the_shapes_the_two_oracles_read_differently(
    tmp_path: Path,
    *,
    name: str,
    source: str,
    expected: Mapping[str, Sequence[int]],
) -> None:
    """What each of the three readers answers where the two oracles part, written out in full.

    Pylint reports a redundant alias, reports a name reached only by an augmented `__all__`, and
    reports a forward reference inside a type alias, while staying quiet about a type-checking
    import nothing annotates. Holding MCMR to Pylint on those four would be holding it to four
    defects, so it follows Ruff and the divergence is measured here rather than asserted.

    The availability probe is the one shape MCMR answers differently from both. Ruff reports it and
    offers `importlib.util.find_spec` in its place, which is advice about how to write the check
    rather than evidence the import is dead, and deleting the statement deletes the check.
    """
    generated = f"{name}.py"
    root = written(tmp_path, {generated: source})

    assert _PYTHON_UNUSED_IMPORT.report(root).states(
        *(Site.at(generated, line) for line in expected["mcmr"])
    )
    assert (
        Oracle.of("ruff", "F401")
        .report(root)
        .states(*(Site.at(generated, line) for line in expected["ruff"]))
    )
    assert (
        Oracle.of("pylint", "unused-import")
        .report(root)
        .states(*(Site.at(generated, line) for line in expected["pylint"]))
    )


def test_unused_import_agrees_with_ruff_over_a_real_checkout() -> None:
    """The check a generated module cannot make, over code somebody wrote for their own reasons.

    Every false positive this rule shipped survived a green generated property and died on the
    first third-party tree it met, because a generator writes the shapes its author thought of and
    a real project writes the ones nobody did. So the corpus is a real checkout named by
    `MCMR_F401_CORPUS`, several separated the way the platform separates a path list, and the case
    skips when the environment names none. Vendoring one instead would make the case hermetic and
    make it stale, and neither MCMR nor Ruff can be pinned by copying somebody else's source into
    this repository.

    The answer is bounded on both sides, since a containment on its own is satisfied by a rule that
    reports nothing at all, which is the failure this whole case exists to catch. Below, everything
    Ruff reports that nobody silenced, minus the availability probes MCMR keeps on purpose and Ruff
    names itself by offering `importlib.util.find_spec` in their place. Above, everything Ruff
    reports once its suppressions are read past, which compares the two analyses rather than the
    two suppression systems, widened by the imports whose bound name their own file states twice. A
    module binding one name from two statements cannot be told which statement supplies it by a
    reader resolving references over the whole module, so MCMR reports both and Ruff hands the
    second to its redefinition rule.
    """
    roots = [
        Path(entry) for entry in os.environ.get("MCMR_F401_CORPUS", "").split(os.pathsep) if entry
    ]
    if not roots or not all(root.is_dir() for root in roots):
        pytest.skip("MCMR_F401_CORPUS names no readable checkout to compare against")

    unsilenced = RuffOracle(rules=["F401"], respect_suppressions=True)
    for root in roots:
        read_past = Oracle.of("ruff", "F401")
        probes = [
            read_past.located(root, found.path, found.line)
            for found in read_past.diagnostics(root)
            if "find_spec" in found.detail
        ]
        ours = _PYTHON_UNUSED_IMPORT.report(root)
        differ(
            ours,
            Relation.SUPERSET,
            unsilenced.report(root).minus(*probes),
            because="MCMR keeps an availability probe Ruff answers by naming `find_spec` instead",
        )
        differ(
            ours,
            Relation.SUBSET,
            read_past.report(root).plus(*repeated(root)),
            because="a name two statements bind cannot be attributed to one of them by a resolver",
        )


def repeated(root: Path) -> list[Site]:
    """Return every import binding whose own file states its bound name more than once."""
    facts = _PYTHON_UNUSED_IMPORT.facts(root)
    stated_twice = Counter((fact.span.path, named(fact)) for fact in facts)
    return [
        Site.at(fact.span.path, fact.span.start_line)
        for fact in facts
        if stated_twice[(fact.span.path, named(fact))] > 1
    ]


def named(fact: Fact) -> str:
    """Return the name one import binding bound, which is the field that family carries."""
    assert isinstance(fact, ImportBindingFact)
    return fact.name
