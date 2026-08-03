from typing import TYPE_CHECKING

from patos import FrozenModel

from ...support import measured
from .data import FindingStatement

if TYPE_CHECKING:
    from mcmr.checking.session import Verdicts
    from mcmr.domain.contracts import Finding


def reported(verdicts: Verdicts, rule_id: str) -> list[Finding]:
    """Return every finding one rule states over the fixture project, in file order."""
    judgment = next(item for item in verdicts.rules if item.definition.id == rule_id)
    return [finding for observation in judgment.failures for finding in observation.findings]


type FindingField = str | bool | dict[str, float]


class Stated(FrozenModel):
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
    finding: FindingStatement

    @property
    def holds(self) -> str:
        """Return evidence the message must include."""
        return self.finding.holds

    @property
    def location(self) -> str:
        """Return the expected finding location."""
        return self.finding.location

    @property
    def measurements(self) -> dict[str, float]:
        """Return exact expected measurements."""
        return self.finding.measurements

    @property
    def message(self) -> str:
        """Return the expected finding message."""
        return self.finding.message

    @property
    def repair(self) -> str:
        """Return the expected repair prompt."""
        return self.finding.repair

    @property
    def rounded(self) -> dict[str, float]:
        """Return measurements compared after rounding."""
        return self.finding.rounded

    @property
    def silent(self) -> bool:
        """Whether the rule should produce no finding."""
        return self.finding.silent

    @classmethod
    def claim(
        cls,
        *,
        rule: str,
        proves: str,
        naming: str = "",
        stated: int | None = None,
        narrowed: int | None = None,
        **finding: FindingField,
    ) -> Stated:
        """Build one rule claim with its finding detail kept cohesive."""
        return cls(
            rule=rule,
            proves=proves,
            naming=naming,
            stated=stated,
            narrowed=narrowed,
            finding=FindingStatement.model_validate(finding),
        )


_CLAIMS: tuple[Stated, ...] = (
    Stated.claim(
        rule="ALL-CLAS0001",
        proves="it used to answer `1` and nothing else, which named no class and no member",
        stated=1,
        message=(
            "`Receipt` declares 3 of its 3 members out of order, and `__init__` belongs where "
            "`total_text` sits"
        ),
        location="shop/records.py:4-19",
        measurements={"declared members": 3, "members out of place": 3},
        repair="Move the first displaced method to its configured position.",
    ),
    Stated.claim(
        rule="ALL-ARCH0003",
        proves="a count of one told a reader nothing about which import pointed the wrong way",
        stated=1,
        message=(
            "`shop` sits at 25 percent instability and imports `labels` at 50 percent "
            "instability, so every change to the second one reaches the 3 packages that "
            "depend on the first"
        ),
        location="shop/records.py:1",
        measurements={
            "instability of the importer": 25.0,
            "instability of the imported": 50.0,
            "packages depending on the importer": 3,
        },
    ),
    Stated.claim(
        rule="ALL-FUNC0001",
        proves="a measure states one finding for every callable, since the number is the answer",
        naming="submit",
        narrowed=1,
        message="`submit` owns 3 direct statements",
        location="shop/api.py:12-18",
        measurements={
            "direct statements": 3,
            "implementation lines": 5,
        },
    ),
    Stated.claim(
        rule="ALL-MODU0001",
        proves="the count alone never said whether a long module was one subject or several",
        naming="api",
        narrowed=1,
        message="`shop/api.py` runs 18 lines holding 0 classes and 2 functions",
        location="shop/api.py:1-19",
        measurements={"physical lines": 18, "classes": 0, "functions": 2},
    ),
    Stated.claim(
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
    Stated.claim(
        rule="ALL-PARA0002",
        proves="this finding only became locatable once the kernel learned to name a parameter",
        stated=1,
        message="`describe` takes `options` as a whole `Options` and reads only `indent`, `width`",
        location="shop/service.py:7",
        measurements={"attributes read": 2, "other operations on it": 0},
    ),
    Stated.claim(
        rule="ALL-FUNC0010",
        proves="a measure that counts every required input names the inputs it counted",
        naming="`charge`",
        message=(
            "`charge` cannot be called without `first`, `second`, `label`, which is 3 parameters "
            "of the 3 it declares"
        ),
        measurements={"parameters a caller has to supply": 3, "parameters declared": 3},
    ),
    Stated.claim(
        rule="ALL-FUNC0010",
        proves="a measure that counts nothing states it in words rather than as an empty list",
        naming="`total_text`",
        message=(
            "`total_text` can be called with nothing, since none of the 1 parameter it declares "
            "is required"
        ),
    ),
    Stated.claim(
        rule="ALL-REAC0002",
        proves="a count of file-local declarations never said which declaration it meant",
        stated=1,
        message=(
            "`shop.service.helper` is a public function read 1 time inside this file and nowhere "
            "outside it"
        ),
        location="shop/service.py:29",
        measurements={"references from its own file": 1, "references from anywhere else": 0},
    ),
    Stated.claim(
        rule="ALL-DUPL0003",
        proves="the number of findings and the value are the same number read two ways",
        stated=1,
        message=(
            "this implementation spans 10 lines and matches the same 66-token normalized "
            "structure as `shop/left.py` at lines 15 to 24"
        ),
        location="shop/right.py:1-10",
        measurements={
            "repeated lines": 10,
            "tokens in the block": 66,
            "copies of it in the tree": 2,
        },
    ),
    Stated.claim(
        rule="ALL-DUPL0004",
        proves="a percentage nobody can divide back out is a number a reader has to trust blindly",
        stated=1,
        message=(
            "10 of the 165 lines this tree holds repeat a block of 10 lines that appears 2 times"
        ),
        location="shop/left.py:15-24",
        rounded={"repeated lines": 10.0, "lines in the tree": 165.0, "share of the tree": 6.0606},
    ),
    Stated.claim(
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
    Stated.claim(
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
    Stated.claim(
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
    Stated.claim(
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
    Stated.claim(
        rule="PY-NAMI0001",
        proves="the table engine attaches the rule's review-only rename plan to its finding",
        stated=1,
        message=(
            "`readable` answers with a Boolean and its name does not say so, since it opens with "
            "none of `is_`, `has_`, `can_`, `should_`, `supports_`"
        ),
        location="shop/service.py:24",
        measurements={"references a rename would move": 0},
        repair="Rename each predicate at its declaration and at every reference bound to it.",
    ),
    Stated.claim(
        rule="PY-IMPO0003",
        proves="the binding carries its declaration node into the attached review-only edit",
        stated=1,
        message="`textwrap` is imported from `textwrap` and nothing in this file reads it",
        location="shop/api.py:1",
        measurements={"references to it": 0},
        repair="Delete the exact import binding that nothing reads.",
    ),
    Stated.claim(
        rule="PY-TEST0004",
        proves="a closed category is one word, and one word cannot say which control is missing",
        stated=1,
        message=(
            "`pyproject.toml` turns on 1 strictness control of the 4 there are, leaving "
            "`strict_markers`, `strict_parametrization_ids`, `strict_xfail` off"
        ),
        location="pyproject.toml:1",
        measurements={"controls turned on": 1, "controls there are": 4},
    ),
)


def claims() -> tuple[Stated, ...]:
    """Return each migrated finding contract in repository execution order."""
    return _CLAIMS


def assert_claim(project: Verdicts, claim: Stated) -> None:
    """Verify one migrated rule's complete finding contract."""
    found = reported(project, claim.rule)
    narrowed = [item for item in found if claim.naming in item.message]
    assert claim.proves, f"{claim.rule} states no reason for its row"
    assert (
        claim.stated is None or len(found) == claim.stated,
        claim.narrowed is None or len(narrowed) == claim.narrowed,
        narrowed[0].message == claim.message,
        not claim.location or narrowed[0].span.location == claim.location,
        not claim.measurements or measured(narrowed[0]) == claim.measurements,
    ) == (True, True, True, True, True), claim.rule
    assert all(
        round(measured(narrowed[0])[name], 4) == value for name, value in claim.rounded.items()
    ), claim.rule
    if claim.silent:
        assert narrowed[0].repair is None, f"{claim.rule} states a repair of its own"
    if claim.repair or claim.holds:
        assert narrowed[0].repair is not None, f"{claim.rule} states no repair"
        assert not claim.repair or narrowed[0].repair.summary == claim.repair, claim.rule
        assert claim.holds in narrowed[0].repair.summary, claim.rule
