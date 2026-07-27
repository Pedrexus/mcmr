from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcmr.facts import CallFact, FunctionFact
from tests.oracle import (
    ClangTidyMagnitudeOracle,
    ClangTidyOracle,
    DeclarationReader,
    FindingReader,
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

pytestmark = [needs_kernel, needs("clang-tidy")]

UNIT = "unit.cpp"
TWIN = "unit.py"
STEP = "    "

COMPLEXITY = ClangTidyMagnitudeOracle(
    rules=("readability-function-cognitive-complexity",),
    settings={"readability-function-cognitive-complexity.Threshold": "0"},
)

# Two of this check's own heuristics have to be turned off before it answers the question MCMR
# answers. It groups parameters whose types merely convert into one another, where MCMR asks for
# the same type written the same way, and it stays silent whenever two names differ enough at
# either end that a caller would notice a transposition. Neither is a disagreement about what a
# swappable parameter is, so both are settings rather than divergences to report.
SWAPPABLE = ClangTidyOracle(
    rules=("bugprone-easily-swappable-parameters",),
    settings={
        "bugprone-easily-swappable-parameters.MinimumLength": "2",
        "bugprone-easily-swappable-parameters.ModelImplicitConversions": "false",
        "bugprone-easily-swappable-parameters.NamePrefixSuffixSilenceDissimilarityTreshold": "0",
    },
)

UNUSED_RESULT = ClangTidyOracle(rules=("bugprone-unused-return-value",))


@pytest.fixture(scope="module")
def trees(tmp_path_factory: pytest.TempPathFactory) -> Trees:
    """Hand every drawn example a tree of its own, since a reading is cached by the tree."""
    return Trees(root=tmp_path_factory.mktemp("clangtidy"))


def braced(depth: int) -> str:
    """Return one C++ callable whose control structures nest exactly this deep."""
    blocks = ("for (int i{0} = 0; i{0} < a; ++i{0}) {{", "if (b > {0}) {{", "while (total < b) {{")
    opening = [f"  {blocks[index % len(blocks)].format(index)}" for index in range(depth)]
    return "\n".join(
        [
            "int score(int a, int b) {",
            "  int total = 0;",
            *opening,
            "    total += 1;",
            "  " + "}" * depth,
            "  return total;",
            "}",
            "",
        ]
    )


def indented(depth: int) -> str:
    """Return the same callable in Python, so one program is stated in both languages."""
    blocks = ("for i{0} in range(a):", "if b > {0}:", "while total < b:")
    opening = [
        f"{STEP * (index + 1)}{blocks[index % len(blocks)].format(index)}"
        for index in range(depth)
    ]
    return "\n".join(
        [
            "def score(a, b):",
            f"{STEP}total = 0",
            *opening,
            f"{STEP * (depth + 1)}total += 1",
            f"{STEP}return total",
            "",
        ]
    )


@settings(max_examples=6, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(min_value=1, max_value=4))
def test_cognitive_complexity_agrees_with_clang_tidy_and_the_python_twin(
    trees: Trees, depth: int
) -> None:
    """One program written twice, so the arithmetic is measured in both frontends.

    `ALL-FUNC0012` scores a structure at one plus the number of structures enclosing it, which is
    Sonar's rule and clang-tidy's, so a chain nesting `depth` deep scores `depth * (depth + 1) / 2`
    and all three readers have to say so. The Python twin independently proves the shared scoring
    model, while the C++ half proves the native provider now supplies the primitive increments the
    general rule reads.
    """
    root = trees.grow({UNIT: braced(depth), TWIN: indented(depth)})
    scored = depth * (depth + 1) // 2
    rule = DeclarationReader(rule_id="ALL-FUNC0012", family=FunctionFact)
    stated = Report(
        reader="the strategy",
        sites=tuple(Site.at(UNIT, 1) for _ in range(scored)),
    )

    oracle = COMPLEXITY.report(root)
    differ(
        stated,
        Relation.EQUALS,
        oracle,
        because="a chain nesting one structure per level scores one more at every level",
    )
    assert (
        rule.model_copy(update={"languages": ("python",)})
        .report(root)
        .states(*(Site(path=TWIN, line=1, through=depth + 4) for _ in range(scored)))
    )
    differ(
        rule.model_copy(update={"languages": ("cpp",)}).report(root),
        Relation.EQUALS,
        oracle,
        because="the native frontend records the same nested structures clang-tidy scores",
    )


def test_swappable_parameters_agrees_with_clang_tidy_on_one_pair(
    tmp_path: Path,
) -> None:
    """A run of two identically typed parameters is one finding to both readers.

    The second callable is what makes this a comparison rather than a coincidence: `int` and
    `double` convert into one another, so clang-tidy groups them until it is told not to and MCMR
    never does, and both readers stay silent about it here.
    """
    root = written(
        tmp_path,
        {
            UNIT: "int pairwise(int a, int b) {\n"
            "  int total = 0;\n"
            "  total += a;\n"
            "  total += b;\n"
            "  return total;\n"
            "}\n"
            "\n"
            "int mixed(int a, double b) {\n"
            "  int total = 0;\n"
            "  total += a;\n"
            "  total += static_cast<int>(b);\n"
            "  return total;\n"
            "}\n"
        },
    )
    oracle = SWAPPABLE.report(root)

    assert oracle.states(Site.at(UNIT, 1))
    differ(
        FindingReader(rule_id="ALL-PARA0001", family=FunctionFact, languages=("cpp",)).report(
            root
        ),
        Relation.EQUALS,
        oracle,
        because="two adjacent parameters of one written type are transposable to both readers",
    )


def test_swappable_parameters_counts_pairs_where_clang_tidy_reports_a_run(
    tmp_path: Path,
) -> None:
    """Three identically typed parameters are one diagnostic there and two pairs here.

    Neither accounting is wrong and the difference is worth pinning rather than tuning away, since
    a project reading a total wants to know whether four interchangeable parameters count as one
    problem or as three. MCMR counts what a caller can transpose, which is the adjacent pairs, so a
    run of `n` is `n - 1` findings and clang-tidy's single diagnostic is credited with the missing
    one by name.
    """
    root = written(
        tmp_path,
        {
            UNIT: "int score(int a, int b, int limit) {\n"
            "  int total = 0;\n"
            "  total += a;\n"
            "  total += b;\n"
            "  total += limit;\n"
            "  return total;\n"
            "}\n"
        },
    )
    oracle = SWAPPABLE.report(root)

    assert oracle.states(Site.at(UNIT, 1))
    differ(
        FindingReader(rule_id="ALL-PARA0001", family=FunctionFact, languages=("cpp",)).report(
            root
        ),
        Relation.EQUALS,
        oracle.plus(Site.at(UNIT, 1)),
        because="clang-tidy reports one run of three where MCMR reports the two pairs inside it",
    )


def test_unused_return_value_agrees_with_clang_tidy(tmp_path: Path) -> None:
    """Both readers report the discarded `strcmp` result and accept the returned one."""
    root = written(
        tmp_path,
        {
            UNIT: "#include <cstring>\n"
            "int discard(const char* left, const char* right) {\n"
            "  std::strcmp(left, right);\n"
            "  return 0;\n"
            "}\n"
            "int keep(const char* left, const char* right) {\n"
            "  return std::strcmp(left, right);\n"
            "}\n"
        },
    )
    oracle = UNUSED_RESULT.report(root)

    assert oracle.states(Site.at(UNIT, 3))
    differ(
        DeclarationReader(
            rule_id="ALL-CALL0001",
            family=CallFact,
            settings={"checked_callables": ("std::strcmp",)},
            languages=("cpp",),
        ).report(root),
        Relation.EQUALS,
        oracle,
        because="the configured result-bearing call is discarded in the first function only",
    )
