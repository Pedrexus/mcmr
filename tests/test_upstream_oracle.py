import os
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcmr.facts import (
    AttributeAccessFact,
    CommentFact,
    ImportBindingFact,
    ModuleFact,
    SyntaxFact,
)
from mcmr.upstream import ClaimIndex, Coverage, ToolCoverage
from tests.oracle import (
    DeclarationReader,
    Oracle,
    RecordReader,
    Relation,
    Report,
    RuffOracle,
    Shape,
    Site,
    Source,
    Trees,
    assembled,
    catalog,
    differ,
    needs,
    needs_kernel,
    written,
)

if TYPE_CHECKING:
    from mcmr.facts import Fact

pytestmark = [needs_kernel, needs("pylint", "ruff")]

GENERATED = "pkg/generated.py"

# Every shape Pylint, Ruff, and MCMR already answer identically. A narrow generator is a weak
# oracle, and the generator this property used to carry only ever wrote `import x` followed by
# `print(x)`, which is why a resolver blind to an `elif` test, an `except` type, a `__future__`
# directive, and a wildcard passed it for as long as it did. Each entry names its own module and
# its own callable so any subset of them assembles into one module that still says what it means.
AGREED: tuple[Shape, ...] = (
    Shape(("import json",), ("def read_call():", "    return json.dumps(1)"), frozenset()),
    Shape(("import math",), (), frozenset({0})),
    Shape(
        ("import re",),
        (
            "def read_elif(value):",
            "    if value == 1:",
            "        return 0",
            "    elif isinstance(value, re.Match):",
            "        return 1",
            "    return 2",
        ),
        frozenset(),
    ),
    Shape(
        ("import decimal",),
        (
            "def read_handler(value):",
            "    try:",
            "        return value",
            "    except decimal.DecimalException:",
            "        return None",
        ),
        frozenset(),
    ),
    Shape(
        ("import string",),
        (
            "def read_match(value):",
            "    match value:",
            "        case string.Template():",
            "            return 1",
            "    return 2",
        ),
        frozenset(),
    ),
    Shape(("from textwrap import *",), (), frozenset()),
    Shape(("import calendar",), ('__all__ = ["calendar"]',), frozenset()),
    Shape(
        ("from typing import TYPE_CHECKING", "", "if TYPE_CHECKING:", "    from uuid import UUID"),
        ("def read_annotation(value: UUID) -> None:", "    return None"),
        frozenset(),
    ),
    Shape(
        ("from pathlib import Path",),
        ('def read_string(value: "Path") -> None:', "    return None"),
        frozenset(),
    ),
    Shape(("from fractions import Fraction",), ("type Ratio = Fraction",), frozenset()),
    Shape(("import gettext as translator",), (), frozenset({0})),
    Shape(
        ("from statistics import mean as average",),
        ("def read_alias(rows):", "    return average(rows)"),
        frozenset(),
    ),
    Shape(("import os.path",), (), frozenset({0})),
    Shape(
        ("from . import sibling",),
        ("def read_sibling():", "    return sibling.VALUE"),
        frozenset(),
    ),
    Shape(("from .sibling import VALUE",), (), frozenset({0})),
)

UNUSED_IMPORT = DeclarationReader(rule_id="PY-IMPO0003", family=ImportBindingFact)
PYTHON_UNUSED_IMPORT = UNUSED_IMPORT.model_copy(update={"languages": ("python",)})


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
    prologue = ("from __future__ import annotations",) if draw(st.booleans()) else ()
    return draw(assembled(AGREED, prologue=prologue))


def package(source: str) -> dict[str, str]:
    """Return the package one generated module needs, so a relative import has somewhere to go."""
    return {
        "pkg/__init__.py": "",
        "pkg/sibling.py": "VALUE = 1\n",
        GENERATED: source,
    }


def expected(source: Source) -> Report:
    """Return what the drawn shapes say about themselves, as a reader of their own."""
    return Report(
        reader="the strategy",
        sites=tuple(Site.at(GENERATED, line) for line in source.reported),
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
        UNUSED_IMPORT.report(root),
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
        PYTHON_UNUSED_IMPORT.report(root),
        Relation.EQUALS,
        oracle,
        because="Ruff cannot open anything but Python, so only the Python facts are compared",
    )


@pytest.mark.parametrize(
    ("name", "source", "ours", "ruff", "pylint"),
    [
        (
            "probe",
            "def run():\n"
            "    try:\n"
            "        import h2\n"
            "    except ImportError:\n"
            '        raise ImportError("install the extra") from None\n'
            "    return 1\n",
            (),
            (3,),
            (),
        ),
        ("redundant_alias", "import json as json\n", (), (), (1,)),
        ("augmented_all", 'import json\n\n__all__ = []\n__all__ += ["json"]\n', (), (), (1,)),
        (
            "aliased_forward",
            'from decimal import Decimal\n\ntype Money = "Decimal"\n',
            (),
            (),
            (1,),
        ),
        (
            "type_only",
            "from typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    from numbers import Number\n",
            (4,),
            (4,),
            (),
        ),
    ],
)
def test_unused_import_reads_the_shapes_the_two_oracles_read_differently(
    tmp_path: Path,
    name: str,
    source: str,
    ours: tuple[int, ...],
    ruff: tuple[int, ...],
    pylint: tuple[int, ...],
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

    assert PYTHON_UNUSED_IMPORT.report(root).states(*(Site.at(generated, line) for line in ours))
    assert (
        Oracle.of("ruff", "F401").report(root).states(*(Site.at(generated, line) for line in ruff))
    )
    assert (
        Oracle.of("pylint", "unused-import")
        .report(root)
        .states(*(Site.at(generated, line) for line in pylint))
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
    stated = os.environ.get("MCMR_F401_CORPUS", "")
    roots = [Path(entry) for entry in stated.split(os.pathsep) if entry]
    if not roots or not all(root.is_dir() for root in roots):
        pytest.skip("MCMR_F401_CORPUS names no readable checkout to compare against")

    unsilenced = RuffOracle(rules=("F401",), respect_suppressions=True)
    for root in roots:
        read_past = Oracle.of("ruff", "F401")
        probes = tuple(
            read_past.located(root, found.path, found.line)
            for found in read_past.diagnostics(root)
            if "find_spec" in found.detail
        )
        ours = PYTHON_UNUSED_IMPORT.report(root)
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


def repeated(root: Path) -> tuple[Site, ...]:
    """Return every import binding whose own file states its bound name more than once."""
    facts = PYTHON_UNUSED_IMPORT.facts(root)
    stated_twice = Counter((fact.span.path, named(fact)) for fact in facts)
    return tuple(
        Site.at(fact.span.path, fact.span.start_line)
        for fact in facts
        if stated_twice[(fact.span.path, named(fact))] > 1
    )


def named(fact: Fact) -> str:
    """Return the name one import binding bound, which is the field that family carries."""
    assert isinstance(fact, ImportBindingFact)
    return fact.name


def test_protected_access_agrees_with_pylint(tmp_path: Path) -> None:
    """The other exact claim, on a fixture stating every way a reach can stay inside its owner.

    Comparing the files both readers named was no comparison at all, since both sides reduce to one
    filename on a one-file tree. The accesses are compared instead, so every way an owner reaches
    its own member has to be allowed by both, and only the two reaches from outside are reported.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "class Engine:\n"
            "    def __init__(self):\n"
            "        self._limit = 3\n"
            "\n"
            "    def run(self):\n"
            "        return self._limit\n"
            "\n"
            "    @classmethod\n"
            "    def build(cls):\n"
            "        return cls._limit\n"
            "\n"
            "    def owner(self):\n"
            "        return Engine._limit\n"
            "\n"
            "    def nested(self):\n"
            "        def inner():\n"
            "            return self._limit\n"
            "\n"
            "        return inner()\n"
            "\n"
            "    def protocol(self):\n"
            "        return self.__class__.__name__\n"
            "\n"
            "\n"
            "class Faster(Engine):\n"
            "    def run(self):\n"
            "        return super()._limit\n"
            "\n"
            "\n"
            "def outside(engine):\n"
            "    engine._limit = 4\n"
            "    return engine._limit\n"
        },
    )
    oracle = Oracle.of("pylint", "protected-access").report(root)

    assert oracle.states(Site.at("generated.py", 31), Site.at("generated.py", 32))
    differ(
        RecordReader(rule_id="ALL-ENCA0001", family=AttributeAccessFact, field="accesses").report(
            root
        ),
        Relation.EQUALS,
        oracle,
        because="every way an owner reaches its own member is owner access to both readers",
    )


def test_protected_access_is_stricter_than_pylint_about_a_base_a_subclass_names(
    tmp_path: Path,
) -> None:
    """Pylint lets a subclass reach a base member by the base's own name, and MCMR does not.

    Owner access under the strict default is `self`, `cls`, `super()`, and the innermost lexical
    class by name. Pylint additionally allows any name a class lists as a base, so a subclass
    reaching `Engine._limit` is silent there and reported here. Naming that one reach keeps the
    relation an equality, where a containment would still have held had MCMR lost the reach from
    the unrelated class as well.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "class Engine:\n"
            "    def __init__(self):\n"
            "        self._limit = 3\n"
            "\n"
            "\n"
            "class Faster(Engine):\n"
            "    def reach(self):\n"
            "        return Engine._limit\n"
            "\n"
            "\n"
            "class Stranger:\n"
            "    def reach(self):\n"
            "        return Engine._limit\n"
        },
    )
    oracle = Oracle.of("pylint", "protected-access").report(root)

    assert oracle.states(Site.at("generated.py", 13))
    differ(
        RecordReader(rule_id="ALL-ENCA0001", family=AttributeAccessFact, field="accesses").report(
            root
        ),
        Relation.EQUALS,
        oracle.plus(Site.at("generated.py", 8)),
        because="Pylint allows a reach through any name a class lists as a base and MCMR does not",
    )


def test_unresolved_work_marker_agrees_with_pylint(tmp_path: Path) -> None:
    """Pylint's default notes are `FIXME`, `XXX`, and `TODO`, so the rule is asked for those.

    MCMR carries `HACK` too, which Ruff reports as `FIX004` and Pylint does not report at all, so
    the setting is narrowed here rather than the fixture being written around the difference.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "# TODO: handle the empty case\n"
            "# rewrite the todo list before shipping\n"
            "\n\n"
            "def load(path):\n"
            "    # FIXME: this loses the encoding\n"
            "    text = read(path)\n"
            "\n"
            "    return text  # XXX later\n"
        },
    )
    oracle = Oracle.of("pylint", "fixme").report(root)
    ours = RecordReader(
        rule_id="ALL-COMM0006",
        family=CommentFact,
        field="groups",
        settings={"markers": ("todo", "fixme", "xxx")},
    ).report(root)

    assert oracle.states(
        Site.at("generated.py", 1), Site.at("generated.py", 6), Site.at("generated.py", 9)
    )
    differ(
        ours,
        Relation.EQUALS,
        oracle,
        because="asked for Pylint's own three notes, the two readers open on the same comments",
    )


def test_the_work_marker_reader_is_wider_than_the_one_pylint_has(tmp_path: Path) -> None:
    """The reader is neutral and every frontend that fills the family widens it for free.

    `unresolved_work_marker` opens on `#`, `//`, and `/*` alike, so the day a frontend fills
    `CommentFact` this rule answers for that language with no change. Pylint can only ever answer
    for Python, so the Rust marker is named in the comparison rather than the relation being
    loosened to a containment any silent reader would satisfy.

    The comments are compared rather than the facts holding them. One `CommentFact` covers a whole
    file, so every fact starts on line one and a containment over fact spans was true whatever
    either reader answered.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "def run():\n    return 1\n\n\n# TODO: python\n",
            "generated.rs": "fn run() {}\n\n// FIXME: rust\n",
        },
    )
    oracle = Oracle.of("pylint", "fixme").report(root)
    ours = RecordReader(rule_id="ALL-COMM0006", family=CommentFact, field="groups").report(root)

    assert oracle.states(Site.at("generated.py", 5))
    differ(
        ours,
        Relation.EQUALS,
        oracle.plus(Site.at("generated.rs", 3)),
        because="the neutral reader answers for Rust as well, where Pylint can only read Python",
    )


def test_non_ascii_source_path_agrees_with_pylint(tmp_path: Path) -> None:
    """On a flat tree the two answer identically, since only the last component differs.

    Both readers judge one file at a time and the paths compared are the ones relative to the tree,
    so the quiet file makes this a real check rather than an arithmetic one. Pylint names the first
    line of the module and MCMR answers for the whole of it, which is what the fold is for.
    """
    root = written(
        tmp_path,
        {"café.py": "def run():\n    return 1\n", "plain.py": "def run():\n    return 2\n"},
    )
    oracle = Oracle.of("pylint", "non-ascii-file-name").report(root)

    assert oracle.states(Site.at("café.py", 1))
    differ(
        DeclarationReader(rule_id="ALL-MODU0004", family=ModuleFact).report(root),
        Relation.EQUALS,
        oracle,
        because="a name a build system cannot reproduce is the same defect to both readers",
    )


def test_non_ascii_source_path_judges_the_directories_pylint_skips(tmp_path: Path) -> None:
    """Pylint judges the module name alone, and a build system reproduces the whole path.

    Every component has to survive an archive, a command line, and another platform's shell, so
    MCMR is deliberately the wider reader and the one module Pylint stays quiet about is named in
    the comparison rather than left to a containment.
    """
    root = written(
        tmp_path,
        {
            "naïve/reader.py": "def run():\n    return 1\n",
            "plain.py": "def run():\n    return 2\n",
        },
    )
    oracle = Oracle.of("pylint", "non-ascii-file-name").report(root)

    assert oracle.states()
    differ(
        DeclarationReader(rule_id="ALL-MODU0004", family=ModuleFact).report(root),
        Relation.EQUALS,
        oracle.plus(Site.at("naïve/reader.py", 1)),
        because="Pylint reads the module name where MCMR reads every component of the path",
    )


def test_dynamic_super_receiver_agrees_with_pylint(tmp_path: Path) -> None:
    """The two arms Pylint reports without inferring anything are the two arms MCMR claims.

    The rule reads one declaration at a time, so the declaration is where a count can be pinned,
    and both arms are their own method here. Comparing the totals alone would have passed on any
    two of the five methods, so Pylint's lines are folded into the methods MCMR reported and each
    one has to hold exactly the findings that method counted.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "class Base:\n"
            "    def run(self):\n"
            "        return 1\n"
            "\n\n"
            "class Engine(Base):\n"
            "    def a(self):\n"
            "        return super(type(self), self).run()\n"
            "\n"
            "    def b(self):\n"
            "        return super(self.__class__, self).run()\n"
            "\n"
            "    def c(self):\n"
            "        return super(Engine, self).run()\n"
            "\n"
            "    def d(self):\n"
            "        return super().run()\n"
            "\n"
            "    def e(self):\n"
            "        return super(Base, self).run()\n"
        },
    )
    oracle = Oracle.of("pylint", "bad-super-call").report(root)

    assert oracle.states(Site.at("generated.py", 8), Site.at("generated.py", 11))
    differ(
        DeclarationReader(rule_id="PY-CLAS0014", family=SyntaxFact).report(root),
        Relation.EQUALS,
        oracle,
        because="a receiver computed at run time is the same defect to both readers",
    )


def test_dynamic_super_receiver_declines_the_arm_that_needs_the_ancestors(tmp_path: Path) -> None:
    """A first argument naming an unrelated class is Pylint's third arm, and MCMR is silent there.

    Telling that apart from a legal skip through the resolution order needs the ancestors of the
    class beside the source of its methods, and no single fact carries both, so the arm is named in
    the comparison rather than the relation being loosened until it says nothing.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "class Base:\n"
            "    def run(self):\n"
            "        return 1\n"
            "\n\n"
            "class Other:\n"
            "    pass\n"
            "\n\n"
            "class Engine(Base):\n"
            "    def run(self):\n"
            "        return super(Other, self).run()\n"
        },
    )
    oracle = Oracle.of("pylint", "bad-super-call").report(root)

    assert oracle.states(Site.at("generated.py", 12))
    differ(
        DeclarationReader(rule_id="PY-CLAS0014", family=SyntaxFact).report(root),
        Relation.EQUALS,
        oracle.minus(Site.at("generated.py", 12)),
        because="a first argument naming an unrelated class needs the ancestors beside the source",
    )


def test_relative_import_beyond_top_level_agrees_with_pylint(tmp_path: Path) -> None:
    """Both halves of this are in the repository, so the answer is arithmetic rather than a guess.

    The tree carries a package initializer and a module beside it, because an initializer is its
    own package and therefore affords one more level than its neighbour does.
    """
    root = written(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/sub/__init__.py": "from .. import first\nfrom ... import second\n",
            "pkg/sub/module.py": "from . import third\nfrom .. import fourth\n"
            "from ... import fifth\n",
        },
    )
    oracle = Oracle.of("pylint", "relative-beyond-top-level").report(root)

    assert oracle.states(Site.at("pkg/sub/__init__.py", 2), Site.at("pkg/sub/module.py", 3))
    differ(
        DeclarationReader(rule_id="PY-IMPO0004", family=ImportBindingFact).report(root),
        Relation.EQUALS,
        oracle,
        because="how many levels a package affords is arithmetic both readers do the same way",
    )


def test_reflective_scope_read_covers_what_pylint_hedges_about(tmp_path: Path) -> None:
    """MCMR names the cause once where Pylint hedges once per name, so the relation is coverage.

    Every `possibly-unused-variable` Pylint reports sits inside a callable MCMR reports, and MCMR
    also reports the reflective callable whose locals all happen to be read, which is the same
    defect with no symptom yet. Asserting equality here would be asserting a coincidence, so the
    containment is the honest relation and the third callable is what makes it a proper one.
    """
    root = written(
        tmp_path,
        {
            "generated.py": "def render(template, title):\n"
            "    prefix = title.upper()\n"
            "    return template.format(**locals())\n"
            "\n\n"
            "def echo(template, title):\n"
            "    return template.format(title, **locals())\n"
            "\n\n"
            "def clean(value):\n"
            "    kept = value * 2\n"
            "    return kept\n"
        },
    )
    oracle = Oracle.of("pylint", "possibly-unused-variable").report(root)
    ours = DeclarationReader(rule_id="ALL-FUNC0015", family=SyntaxFact).report(root)

    assert oracle.states(Site.at("generated.py", 2))
    assert len(set(ours.sites)) == 2
    differ(
        ours,
        Relation.SUPERSET,
        oracle,
        because="MCMR names the reflective read once where Pylint hedges once per local it sees",
    )


def test_every_native_claim_is_covered_by_a_case() -> None:
    """A message claimed natively with no case behind it is an assertion, not a measurement.

    Each claim names the file holding its differential case, and the file is opened rather than
    trusted, so deleting a case turns the claim it backed red instead of leaving it standing.
    """
    exercised = {
        "unused-import": "test_upstream_oracle.py",
        "protected-access": "test_upstream_oracle.py",
        "fixme": "test_upstream_oracle.py",
        "non-ascii-file-name": "test_upstream_oracle.py",
        "bad-super-call": "test_upstream_oracle.py",
        "relative-beyond-top-level": "test_upstream_oracle.py",
        "duplicate-code": "test_clone_rules.py",
        "too-many-public-methods": "test_design_measure_oracle.py",
        "too-many-ancestors": "test_design_measure_oracle.py",
        "abstract-method": "test_override_rules.py",
        "arguments-differ": "test_override_rules.py",
        "arguments-renamed": "test_override_rules.py",
        "invalid-overridden-method": "test_override_rules.py",
        "method-hidden": "test_override_rules.py",
        "non-parent-init-called": "test_override_rules.py",
        "overridden-final-method": "test_override_rules.py",
        "signature-differs": "test_override_rules.py",
        "subclassed-final-class": "test_override_rules.py",
        "super-init-not-called": "test_override_rules.py",
    }
    definitions = tuple(catalog().definitions)
    account = ToolCoverage(tool="pylint", claims=ClaimIndex(definitions=definitions))
    native = {entry.rule.symbol for entry in account.entries if entry.coverage is Coverage.NATIVE}

    assert set(exercised) <= native
    for symbol, case in exercised.items():
        assert (Path(__file__).parent / case).exists(), f"{symbol} names a case that is gone"
    assert native - set(exercised) == {
        "cyclic-import",
        "unused-private-member",
        "useless-parent-delegation",
    }, sorted(native - set(exercised))
