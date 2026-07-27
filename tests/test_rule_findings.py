from typing import TYPE_CHECKING

import pytest

from mcmr.backends import ClassificationBackend
from mcmr.bases import FrozenFlexModel
from mcmr.facts import (
    DesignStructureFact,
    Evidence,
    FileHistory,
    RepositoryHistoryFact,
    SourceSpan,
)
from mcmr.models import explained, reports_findings
from mcmr.rules.general.deterministic.history.r0001 import large_file_the_team_keeps_reopening
from mcmr.rules.general.llm.design.r2001 import primitive_obsession
from tests.conftest import measured, needs_kernel, streams, synchronous, written

if TYPE_CHECKING:
    from enum import StrEnum

    from mcmr.catalog import Catalog
    from mcmr.facts import Fact
    from mcmr.models import Finding, RuleContract, RuleDefinition

# Which families answer for a whole repository rather than for one file, so the guard below can
# check the migrated slice still holds one of each.
WIDE = frozenset(
    {
        "CloneGroupFact",
        "DependencyComponentFact",
        "ModuleCouplingFact",
        "RepositoryHistoryFact",
    }
)

# One project written so that every migrated rule reading source has something real to report. It
# is deliberately one project rather than one snippet per rule, because a finding has to name the
# right thing inside a file that also holds things it must stay quiet about.
FIXTURE: dict[str, str] = {
    "pyproject.toml": (
        "[project]\n"
        'name = "shop"\n'
        'requires-python = ">=3.14"\n\n'
        "[tool.pytest.ini_options]\n"
        'addopts = "-q --strict-config"\n'
    ),
    "shop/__init__.py": "",
    "shop/labels.py": (
        "from .settings import Options\n\n\n"
        "def label(options: Options) -> str:\n"
        '    """Name one column."""\n'
        "    return str(options.width)\n"
    ),
    "shop/records.py": (
        "from .labels import label\n\n\n"
        "class Receipt:\n"
        '    """Hold what one order was charged."""\n\n'
        "    total: int = 0\n"
        "    currency: str = 'JPY'\n\n"
        "    def total_text(self) -> str:\n"
        '        """Return the amount as text."""\n'
        '        return f"{self.total} {self.currency}"\n\n'
        "    def __init__(self, total: int = 0) -> None:\n"
        "        self.total = total\n\n"
        "    def named(self) -> str:\n"
        '        """Return the label this receipt prints under."""\n'
        "        return label(Options())\n"
    ),
    "shop/settings.py": (
        "class Options:\n"
        '    """Hold every knob one render takes."""\n\n'
        "    width: int = 80\n"
        "    indent: int = 2\n"
    ),
    "shop/service.py": (
        "from json import dumps\n\n"
        "from .records import Receipt\n"
        "from .settings import Options\n\n\n"
        "def describe(options: Options) -> str:\n"
        '    """Render one receipt.\n\n'
        "    Args:\n"
        "        options: the knobs.\n"
        '    """\n'
        '    return f"{options.width}:{options.indent}"\n\n\n'
        "def charge(first: Receipt, second: Receipt, label: str) -> int:\n"
        '    """Add two receipts together."""\n'
        "    t = first.total + second.total\n"
        "    if label:\n"
        "        return t\n"
        "    return t\n\n\n"
        "def readable(rows: list) -> bool:\n"
        '    """Whether every row is short enough to print."""\n'
        "    return all(len(row) < 80 for row in rows)\n\n\n"
        "def helper(value: str) -> str:\n"
        '    """Return the value unchanged."""\n'
        "    return value\n\n\n"
        "def render(receipt: Receipt) -> str:\n"
        '    """Return one receipt as a line."""\n'
        "    return helper(dumps({'total': receipt.total}))\n"
    ),
    "shop/types.py": (
        "from pydantic import BaseModel\n\n\n"
        "class OrderLine(BaseModel):\n"
        '    """One line of one order."""\n\n'
        "    total: int\n"
    ),
    "shop/api.py": (
        "import textwrap\n\n"
        "from .records import Receipt\n"
        "from .types import OrderLine\n\n\n"
        "def owed(line: OrderLine) -> int:\n"
        '    """Return what one line owes."""\n'
        "    return line.total\n\n\n"
        "def submit(receipt: Receipt) -> str:\n"
        '    """Submit one receipt and name what came back."""\n'
        "    if receipt.total < 0:\n"
        '        return "rejected"\n'
        "    if receipt.total == 0:\n"
        '        return "empty"\n'
        '    return "placed"\n'
    ),
    "shop/left.py": (
        "from .records import Receipt\n"
        "from .types import OrderLine\n\n\n"
        "def billed(line: OrderLine) -> int:\n"
        '    """Return what one line was billed."""\n'
        "    return line.total\n\n\n"
        "def paid(receipt: Receipt) -> int:\n"
        '    """Return what one receipt came to."""\n'
        "    return receipt.total\n\n\n"
        "def audit(rows: list[str]) -> int:\n"
        '    """Count the rows that say something."""\n'
        "    total = 0\n"
        "    for row in rows:\n"
        "        if not row:\n"
        "            continue\n"
        "        if row.startswith('#'):\n"
        "            continue\n"
        "        total = total + len(row) + len(row.strip()) + len(row.lstrip())\n"
        "    return total\n"
    ),
    "shop/right.py": (
        "def review(rows: list[str]) -> int:\n"
        '    """Count the rows that say something."""\n'
        "    total = 0\n"
        "    for row in rows:\n"
        "        if not row:\n"
        "            continue\n"
        "        if row.startswith('#'):\n"
        "            continue\n"
        "        total = total + len(row) + len(row.strip()) + len(row.lstrip())\n"
        "    return total\n"
    ),
    "shop/prose.py": (
        "def opened() -> str:\n"
        '    """Return the name this shop opened under."""\n'
        '    return "shop"\n\n\n'
        "def closed() -> str:\n"
        '    """Return the name this shop closed under."""\n'
        '    return "shop"\n\n\n'
        "def widest() -> int:\n"
        '    """Return the widest column this shop prints."""\n'
        "    return 80\n\n\n"
        "def narrowest() -> int:\n"
        '    """Return the narrowest column this shop prints."""\n'
        "    return 20\n\n\n"
        "def counted() -> int:\n"
        '    """Return how many receipts this shop holds."""\n'
        "    return 0\n\n\n"
        "def totalled() -> int:\n"
        '    """Return what every receipt comes to together."""\n'
        "    return 0\n\n\n"
        "def explain() -> str:\n"
        '    """Say what this module is here to do."""\n'
        '    return "shop"\n'
    ),
}


@pytest.fixture(scope="module")
def project(
    tmp_path_factory: pytest.TempPathFactory, catalog: Catalog
) -> dict[type[Fact], list[Fact]]:
    """Build every fact family the fixture project supports, once for the whole module."""
    root = written(tmp_path_factory.mktemp("findings"), FIXTURE)
    return streams(root, catalog.rules)


def contract(catalog: Catalog, rule_id: str) -> tuple[RuleContract, RuleDefinition]:
    """Return the callable and the definition of one rule, by its identifier."""
    definition = next(item for item in catalog.definitions if item.id == rule_id)
    rule = next(item for item in catalog.rules if item.callable_path == definition.callable)
    return rule, definition


def reported(
    catalog: Catalog, streams: dict[type[Fact], list[Fact]], rule_id: str
) -> list[Finding]:
    """Return every finding one rule states over the fixture project, in file order."""
    rule, definition = contract(catalog, rule_id)
    stream = next(family for family in streams if family.__name__ == definition.fact)
    return [
        finding
        for fact in sorted(streams[stream], key=lambda item: item.key)
        for finding in explained(synchronous(rule.invoke(fact, settings={}, dependencies={})))
    ]


# Which rules have migrated to answering with findings, and what each one proves about the shape.
# The guard below reads this in both directions, so a rule that migrates without an entry and an
# entry whose rule went back to a bare value are both failures. What is left over is the gap.
MIGRATED: dict[str, str] = {
    "ALL-ARCH0011": "a count whose findings are the components of a repository-wide graph",
    "ALL-ARCH0012": "a count over a repository-wide fact",
    "ALL-ARCH0013": "an occurrence over a repository-wide fact",
    "ALL-CLAS0002": "a count over a per-file fact whose records carry their own range",
    "ALL-DUPL0003": "a count whose findings are one per record rather than one per fact",
    "ALL-DUPL0004": "a percentage over the same records",
    "ALL-FUNC0001": "a measure whose finding is the measurement itself",
    "ALL-FUNC0014": "a measure whose message changes shape when it counts nothing",
    "ALL-HIST0001": "a count over the recorded history of a repository",
    "ALL-MODU0001": "a measure over a whole module",
    "ALL-NAMI0001": "a count reading the syntax tree, located at the node it read",
    "ALL-PARA0001": "a count over the parameters one callable declares",
    "ALL-PARA0002": "a count over records the kernel had to learn to locate",
    "ALL-REAC0002": "a count over the reach of what a module declares",
    "ALL-WRIT0005": "a percentage the rule takes the maximum of",
    "ALL-DESI2001": "the model lane, where the finding cites the claims the judgment read",
    "PY-COLL0001": "a bare Boolean rather than a declared occurrence",
    "PY-DOCU0001": "a Boolean whose findings say which of two shapes broke",
    "PY-IMPO0003": "an occurrence whose repair comes from the fix the rule already declares",
    "PY-MODE0003": "a count over declarative models",
    "PY-NAMI0002": "an occurrence whose declared fix is a review rather than a safe edit",
    "PY-TEST0012": "a closed category",
    "RS-LIFE0001": "a count over records located by line inside a whole-module fact",
    "RS-LIFE0002": "a count whose records are the subset of a wider list that qualified",
    "RS-LIFE0003": "a measure whose findings are every record it counted, with no repair",
    "RS-OWNE0001": "a count whose repair is a choice between three different edits",
    "RS-OWNE0002": "a measure read beside its counterpart rather than on its own",
    "TS-MODU0001": "a count over the specifiers a module names rather than over a number",
    "TS-MODU0002": "a measure stating one finding for the record that produced the maximum",
    "TS-TYPE0001": "a count over records a frontend had to learn to look through an export for",
    "TS-TYPE0002": "a percentage whose findings are the occurrences behind the share",
}


class Stated(FrozenFlexModel):
    """What one migrated rule has to say about the fixture project, and why that sentence matters.

    Nineteen rules used to prove this in nineteen bodies that differed only in their literals, so
    the shape of the claim was spread across three hundred lines and the interesting part, which is
    the sentence each rule now says instead of a number, was the hardest thing to read. Stating the
    claims as rows puts every one of them on the page at once.
    """

    rule: str
    proves: str
    naming: str = ""
    stated: int | None = None
    narrowed: int | None = None
    message: str
    location: str = ""
    measurements: dict[str, float] = {}
    rounded: dict[str, float] = {}
    repair: str = ""
    holds: str = ""
    silent: bool = False


CLAIMS: tuple[Stated, ...] = (
    Stated(
        rule="ALL-CLAS0002",
        proves="it used to answer `1` and nothing else, which named no class and no member",
        stated=1,
        message=(
            "`Receipt` declares 3 of its 3 members out of order, and `__init__` belongs where "
            "`total_text` sits"
        ),
        location="shop/records.py:4-19",
        measurements={"declared members": 3, "members out of place": 3},
        repair=(
            "put `__init__` before `total_text` (reorder the members or open a named region "
            "where this order is deliberate)"
        ),
    ),
    Stated(
        rule="ALL-ARCH0013",
        proves="it used to answer `True`, which is the least a finding can say",
        stated=1,
        message=(
            "`shop.records` is imported by 3 modules and 0 of the 1 type it declares state a "
            "contract, so every one of those importers is wired to an implementation"
        ),
        location="shop/records.py:1",
        measurements={
            "modules depending on it": 3,
            "types it declares": 1,
            "of them stating a contract": 0,
            "distance from the main sequence": 75.0,
        },
        holds="something abstract to depend on",
    ),
    Stated(
        rule="ALL-ARCH0012",
        proves="a count of one told a reader nothing about which import pointed the wrong way",
        stated=1,
        message=(
            "`shop.records` sits at 25 percent instability and imports `shop.labels` at 50 "
            "percent instability, so every change to the second one reaches the 3 modules that "
            "depend on the first"
        ),
        location="shop/records.py:1",
        measurements={
            "instability of the importer": 25.0,
            "instability of the imported": 50.0,
            "modules depending on the importer": 3,
        },
    ),
    Stated(
        rule="ALL-FUNC0001",
        proves="a measure states one finding for every callable, since the number is the answer",
        naming="submit",
        narrowed=1,
        message="`submit` runs 5 lines of implementation over 3 statements of its own",
        location="shop/api.py:12-18",
        measurements={
            "implementation lines": 5,
            "statements in the body": 3,
            "places it branches": 2,
        },
    ),
    Stated(
        rule="ALL-MODU0001",
        proves="the count alone never said whether a long module was one subject or several",
        naming="api",
        narrowed=1,
        message="`shop/api.py` runs 18 lines holding 0 classes and 2 functions",
        location="shop/api.py:1-19",
        measurements={"physical lines": 18, "classes": 0, "functions": 2},
    ),
    Stated(
        rule="ALL-PARA0001",
        proves="two parameters a caller can transpose is a defect nobody can act on unnamed",
        stated=1,
        message=(
            "`charge` takes `first` and `second` next to each other and both are `Receipt`, so a "
            "caller can transpose them silently"
        ),
        location="shop/service.py:16-21",
        measurements={
            "position in the parameter list": 1,
            "parameters a caller can pass by position": 3,
        },
    ),
    Stated(
        rule="ALL-PARA0002",
        proves="this finding only became locatable once the kernel learned to name a parameter",
        stated=1,
        message="`describe` takes `options` as a whole `Options` and reads only `indent`, `width`",
        location="shop/service.py:7",
        measurements={"attributes read": 2, "other operations on it": 0},
    ),
    Stated(
        rule="ALL-FUNC0014",
        proves="a measure that counts every required input names the inputs it counted",
        naming="`charge`",
        message=(
            "`charge` cannot be called without `first`, `second`, `label`, which is 3 parameters "
            "of the 3 it declares"
        ),
        measurements={"parameters a caller has to supply": 3, "parameters declared": 3},
    ),
    Stated(
        rule="ALL-FUNC0014",
        proves="a measure that counts nothing states it in words rather than as an empty list",
        naming="`total_text`",
        message=(
            "`total_text` can be called with nothing, since none of the 1 parameter it declares "
            "is required"
        ),
    ),
    Stated(
        rule="ALL-REAC0002",
        proves="a count of file-local declarations never said which declaration it meant",
        stated=1,
        message=(
            "`shop.service.helper` is a public function read 1 time inside this file and nowhere "
            "outside it"
        ),
        location="shop/service.py:1",
        measurements={"references from its own file": 1, "references from anywhere else": 0},
    ),
    Stated(
        rule="ALL-DUPL0003",
        proves="the number of findings and the value are the same number read two ways",
        stated=1,
        message=(
            "this implementation spans 10 lines and repeats the same 66-token normalized "
            "structure as `shop/left.py` at lines 15 to 24"
        ),
        location="shop/right.py:1-10",
        measurements={
            "repeated lines": 10,
            "tokens in the block": 66,
            "copies of it in the tree": 2,
        },
    ),
    Stated(
        rule="ALL-DUPL0004",
        proves="a percentage nobody can divide back out is a number a reader has to trust blindly",
        stated=1,
        message=(
            "10 of the 158 lines this tree holds repeat a block of 10 lines that appears 2 times"
        ),
        location="shop/left.py:15-24",
        rounded={"repeated lines": 10.0, "lines in the tree": 158.0, "share of the tree": 6.3291},
    ),
    Stated(
        rule="ALL-WRIT0005",
        proves="the value is the highest concentration and the finding is what produced it",
        stated=1,
        message="6 of the 7 sentences in one section open with `return`",
        location="shop/prose.py:1-34",
        rounded={
            "sentences opening the same way": 6.0,
            "sentences read": 7.0,
            "share of the section": 85.7143,
        },
    ),
    Stated(
        rule="ALL-NAMI0001",
        proves="the syntax tree carries a span per node, so this finding is the exact line",
        stated=1,
        message=(
            "`charge` binds `t`, which is shorter than the 3 characters a name needs to say what "
            "it holds"
        ),
        location="shop/service.py:18",
        measurements={"characters in the name": 1, "characters a name needs here": 3},
    ),
    Stated(
        rule="PY-DOCU0001",
        proves="one Boolean covered two independent defects a reader could not tell apart",
        stated=1,
        message=(
            "the docstring of `describe` carries a heading or a label where this project writes "
            "plain lines"
        ),
        location="shop/service.py:7-13",
        measurements={"characters in the summary": 19, "characters this project accepts": 99},
    ),
    Stated(
        rule="PY-COLL0001",
        proves="answering `True` for a whole file named none of the three parameters it meant",
        naming="`readable`",
        stated=3,
        message=(
            "`readable` declares `rows` as a `list` and never does anything only a `list` can do"
        ),
        location="shop/service.py:24",
        measurements={"operations on it": 1, "of them needing the concrete type": 0},
    ),
    Stated(
        rule="PY-NAMI0002",
        proves="a rule with a fix states no repair of its own, since the engine attaches the fix",
        stated=1,
        message=(
            "`readable` answers with a Boolean and its name does not say so, since it opens with "
            "none of `is_`, `has_`, `can_`, `should_`, `supports_`"
        ),
        location="shop/service.py:24",
        measurements={"references a rename would move": 0},
        silent=True,
    ),
    Stated(
        rule="PY-IMPO0003",
        proves="the binding carries its own declaration node, so this finding is exact",
        stated=1,
        message="`textwrap` is imported from `textwrap` and nothing in this file reads it",
        location="shop/api.py:1",
        measurements={"references to it": 0},
        silent=True,
    ),
    Stated(
        rule="PY-MODE0003",
        proves="a count of misplaced models named neither the model nor where it belongs",
        stated=1,
        message=(
            "`OrderLine` is a record with no behavior that 2 modules import, and the file its "
            "readers share is `shop/models.py` rather than `shop/types.py`"
        ),
        location="shop/types.py:4-7",
        measurements={"modules importing it": 2, "fields it declares": 1},
    ),
    Stated(
        rule="PY-TEST0012",
        proves="a closed category is one word, and one word cannot say which control is missing",
        stated=1,
        message=(
            "`pyproject.toml` turns on 0 strictness controls of the 4 there are, leaving "
            "`strict_config`, `strict_markers`, `strict_parametrization_ids`, `strict_xfail` off"
        ),
        location="pyproject.toml:1",
        measurements={"controls turned on": 0, "controls there are": 4},
    ),
)


@needs_kernel
def test_every_migrated_rule_says_the_sentence_it_claims_about_the_fixture_project(
    catalog: Catalog, project: dict[type[Fact], list[Fact]]
) -> None:
    """Each row is one rule's whole finding, read back off a repository written to provoke it.

    A finding has to name the right thing inside a file that also holds things the rule must stay
    quiet about, which is why this is one project rather than one snippet per rule. The message,
    the place, the numbers behind it, and whether the repair is the rule's own or the fix it
    already declares are all checked, since a finding right about three of those and wrong about
    the fourth is still a finding nobody can act on.
    """
    for claim in CLAIMS:
        found = reported(catalog, project, claim.rule)
        narrowed = [item for item in found if claim.naming in item.message]

        assert claim.proves, f"{claim.rule} states no reason for its row"
        assert claim.stated is None or len(found) == claim.stated, (
            f"{claim.rule} stated {len(found)} findings rather than {claim.stated}"
        )
        assert claim.narrowed is None or len(narrowed) == claim.narrowed, (
            f"{claim.rule} narrowed to {len(narrowed)} findings rather than {claim.narrowed}"
        )
        assert narrowed[0].message == claim.message, claim.rule
        assert not claim.location or narrowed[0].span.location == claim.location, claim.rule
        assert not claim.measurements or measured(narrowed[0]) == claim.measurements, claim.rule
        assert all(
            round(measured(narrowed[0])[name], 4) == value for name, value in claim.rounded.items()
        ), claim.rule
        if claim.silent:
            assert narrowed[0].repair is None, f"{claim.rule} states a repair of its own"
        if claim.repair or claim.holds:
            assert narrowed[0].repair is not None, f"{claim.rule} states no repair"
            assert not claim.repair or narrowed[0].repair.summary == claim.repair, claim.rule
            assert claim.holds in narrowed[0].repair.summary, claim.rule


def test_the_history_rule_names_the_file_and_what_keeps_bringing_people_back() -> None:
    """No repository this suite writes has a history, so the recorded evidence is stated here."""
    subject = RepositoryHistoryFact(
        key="history:shop",
        span=SourceSpan(path=".git"),
        commit_count=40,
        files=[
            FileHistory(path="shop/service.py", commit_count=30, line_count=620, author_count=6),
            FileHistory(path="shop/api.py", commit_count=2, line_count=800, author_count=1),
        ],
    )

    answer = large_file_the_team_keeps_reopening(subject)

    assert answer.value == 1
    assert answer.findings[0].message == (
        "`shop/service.py` runs 620 lines and took 30 commits against the 30 the busiest file "
        "took, the last of them 0 days ago"
    )
    assert answer.findings[0].span.location == "shop/service.py:1"
    assert measured(answer.findings[0]) == {
        "lines": 620,
        "commits": 30,
        "commits the busiest file took": 30,
        "days since the last one": 0,
    }


class FirstCategory(ClassificationBackend):
    """Answer with the first category of whatever rubric a rule states."""

    async def classify[Category: StrEnum](
        self, subject: Fact, *, category: type[Category], instructions: str
    ) -> Category:
        """Return the first allowed category, which is all a lane test needs from a model."""
        assert instructions
        assert subject.key
        return next(iter(category))


@pytest.mark.anyio
async def test_the_model_lane_carries_the_claims_its_judgment_read() -> None:
    """A judgment nobody can reproduce is only worth reading beside the evidence it saw."""
    subject = DesignStructureFact(
        key="design:shop/service.py",
        span=SourceSpan(path="shop/service.py", start_line=4, end_line=30),
        evidence=[
            Evidence(signal="repeated_validation", detail="two sites", source="kernel"),
            Evidence(signal="parameter_group", detail="amount and currency", source="kernel"),
        ],
    )

    answer = await primitive_obsession(subject, FirstCategory())

    assert answer.value == "appropriate"
    assert answer.findings[0].message == (
        "the judgment backend read `design:shop/service.py` as `appropriate` from 2 retained "
        "claims, which are `repeated_validation`, `parameter_group`"
    )
    assert answer.findings[0].span.location == "shop/service.py:4-30"
    assert measured(answer.findings[0]) == {"retained claims": 2}
    assert answer.findings[0].repair is not None
    assert answer.findings[0].repair.summary.startswith("check `appropriate` against")


def test_the_ledger_names_exactly_the_rules_that_answer_with_findings(catalog: Catalog) -> None:
    """The gap has to be visible and shrinking rather than forgotten.

    This fails in both directions. A rule that migrates without an entry is unrecorded work, and
    an entry whose rule went back to a bare value is a claim about the catalog that stopped being
    true, which is the shape every stale allowance takes.
    """
    reporting = {
        definition.id
        for definition in catalog.definitions
        for candidate in (contract(catalog, definition.id)[0],)
        if reports_findings(candidate.hints["return"])
    }

    assert reporting == set(MIGRATED)
    assert all(reason for reason in MIGRATED.values())
    assert len(catalog.definitions) - len(MIGRATED) == 246


def test_the_migrated_slice_still_covers_every_shape_a_rule_can_take(catalog: Catalog) -> None:
    """A slice that drifted into one shape would stop proving the seam holds for the others.

    Each of these is a case the migration had to answer differently, so the recipe a following
    agent applies is only trustworthy while every one of them has a worked example in the tree.
    """
    migrated = [item for item in catalog.definitions if item.id in MIGRATED]
    covered = {
        "count": [item for item in migrated if item.output == "int"],
        "percentage": [item for item in migrated if item.output == "float"],
        "occurrence": [item for item in migrated if item.output == "bool" and item.unit],
        "bare boolean": [item for item in migrated if item.output == "bool" and not item.unit],
        "category": [item for item in migrated if item.output == "category"],
        "repository-wide fact": [item for item in migrated if item.fact in WIDE],
        "per-file fact": [item for item in migrated if item.fact not in WIDE],
        "carries an autofix": [item for item in migrated if item.fixes],
        "model lane": [item for item in migrated if item.lane != "deterministic"],
    }

    assert {shape for shape, found in covered.items() if not found} == set()
