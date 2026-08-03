from typing import TYPE_CHECKING

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mcmr.facts import FunctionFact, ModuleSurfaceFact, SyntaxFact

from ..oracle import (
    DeclarationReader,
    ESLintMagnitudeOracle,
    ESLintOracle,
    FindingReader,
    Oracle,
    Relation,
    Site,
    Trees,
    differ,
    needs,
    needs_kernel,
    written,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [needs_kernel, needs("eslint")]

_MODULE = "app.ts"
_BLOCKS = (
    "for (let i{0} = 0; i{0} < 3; i{0}++) {{",
    "if (value > {0}) {{",
    "while (value > {0}) {{",
)


@pytest.fixture(scope="module")
def trees(tmp_path_factory: pytest.TempPathFactory) -> Trees:
    """Hand every drawn example a tree of its own, since a reading is cached by the tree."""
    return Trees(root=tmp_path_factory.mktemp("eslint"))


def nested(depth: int) -> str:
    """Return one callable whose blocks nest exactly this deep, opening one block per line.

    Each block opens on the line after the one holding it, so the line a block opens on is `depth`
    lines below the declaration and both readers can be asked about a place rather than a total.
    """
    opening = [f"  {_BLOCKS[index % len(_BLOCKS)].format(index)}" for index in range(depth)]
    closing = ["  " + "}" * depth] if depth else []
    return "\n".join(
        [
            "export function deep(value: number): number {",
            *opening,
            f"    value += {depth};",
            *closing,
            "  return value;",
            "}",
            "",
        ]
    )


@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(min_value=1, max_value=5))
def test_nesting_depth_is_the_ceiling_eslint_falls_silent_at(trees: Trees, depth: int) -> None:
    """Compare the nesting ceilings ESLint and MCMR enforce.

    ESLint counts blocks from one and MCMR counts what encloses a structure, so they differ by
    exactly one and neither locates its finding in the same place. The external finding names the
    block while `FunctionFact` names the declaration.

    What is compared instead is the ceiling, which is the one thing both readers mean identically.
    MCMR measures `depth - 1` at the callable exactly when ESLint reports nothing at a maximum of
    `depth` and reports the innermost block alone at a maximum of `depth - 1`. That is the whole
    claim, and it is worth stating because a project porting a `max-depth` of four to MCMR has to
    write three.
    """
    root = trees.grow({_MODULE: nested(depth)})
    ours = DeclarationReader(rule_id="ALL-FUNC0009", family=FunctionFact, suffixes=(".ts",))

    declaration = Site(path=_MODULE, line=1, through=depth + 5)
    assert ours.report(root).states(*(declaration for _ in range(depth - 1)))
    assert ESLintOracle(rules=("max-depth",), ceiling=depth).report(root).states()
    assert (
        ESLintOracle(rules=("max-depth",), ceiling=depth - 1)
        .report(root)
        .states(Site.at(_MODULE, depth + 1))
    )


@settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.integers(min_value=0, max_value=5))
def test_required_parameter_count_agrees_with_typescript_eslint(trees: Trees, width: int) -> None:
    """MCMR generalizes `@typescript-eslint/max-params`, so it owes that rule's own magnitude.

    Both readers locate the finding at the declaration and both count the parameters a signature
    declares, so the comparison is an equality of magnitudes with the ceiling driven to zero. A
    parameter carrying a default is what would part them, since MCMR counts only what a caller has
    to supply, and this corpus deliberately declares none so the equality is the honest assertion.
    """
    parameters = ", ".join(f"a{index}: number" for index in range(width))
    root = trees.grow(
        {_MODULE: f"export function take({parameters}): number {{\n  return 1;\n}}\n"}
    )
    oracle = ESLintMagnitudeOracle(rules=("@typescript-eslint/max-params",), ceiling=0)

    differ(
        DeclarationReader(rule_id="ALL-FUNC0010", family=FunctionFact, suffixes=(".ts",)).report(
            root
        ),
        Relation.EQUALS,
        oracle.report(root),
        because="every parameter drawn here is required, which is what both readers then count",
    )


def test_escape_hatch_density_covers_two_typescript_eslint_rules_and_the_assertion(
    tmp_path: Path,
) -> None:
    """MCMR reads four hatches where ESLint splits them across three rules and a comment plugin.

    `no-explicit-any` and `no-non-null-assertion` are the two MCMR claims, and it also counts the
    `as` assertion that ESLint hands to `consistent-type-assertions`. Naming that third hatch keeps
    the relation an equality, and it is the honest shape because `x = 1 as any` is two hatches on
    one line rather than one: the promise the assertion makes and the type it promises.
    """
    root = written(
        tmp_path,
        {
            _MODULE: """export function widen(value: unknown): string {
  const loose = value as any;
  return loose!.name;
}
"""
        },
    )
    oracle = Oracle.of(
        "eslint",
        "@typescript-eslint/no-explicit-any",
        "@typescript-eslint/no-non-null-assertion",
    ).report(root)

    assert oracle.states(Site.at(_MODULE, 2), Site.at(_MODULE, 3))
    differ(
        FindingReader(rule_id="TS-TYPE0002", family=ModuleSurfaceFact, suffixes=(".ts",)).report(
            root
        ),
        Relation.EQUALS,
        oracle.plus(Site.at(_MODULE, 2)),
        because="MCMR counts the `as` assertion ESLint hands to consistent-type-assertions",
    )


def test_the_console_and_debugger_claims_equal_the_eslint_union(
    tmp_path: Path,
) -> None:
    """One general rule answers the union of the two artifacts ESLint keeps separate.

    The same program in Python proves the rule is still language neutral, while the TypeScript
    half proves the provider now supplies the evidence needed by the two claims it makes.
    """
    root = written(
        tmp_path,
        {
            _MODULE: """export function run(value: number): number {
  console.log(value);
  debugger;
  return value;
}
""",
            "app.py": "def run(value):\n    print(value)\n    breakpoint()\n    return value\n",
        },
    )
    artifacts = DeclarationReader(rule_id="ALL-CONT0003", family=SyntaxFact)

    console = Oracle.of("eslint", "no-console").report(root)
    debugger = Oracle.of("eslint", "no-debugger").report(root)
    assert console.states(Site.at(_MODULE, 2))
    assert debugger.states(Site.at(_MODULE, 3))
    reached = Site(path="app.py", line=1, through=4)
    python = artifacts.model_copy(update={"languages": ("python",)})
    assert python.report(root).states(reached, reached)
    differ(
        artifacts.model_copy(update={"languages": ("typescript",)}).report(root),
        Relation.UNION,
        console,
        debugger,
        because="console calls and debugger statements are the two artifact forms the rule joins",
    )


def test_the_unused_expression_claim_agrees_with_eslint(
    tmp_path: Path,
) -> None:
    """Both readers find the bare member and comparison and leave the returned member alone."""
    root = written(
        tmp_path,
        {
            _MODULE: """export function run(order: {total: number}): number {
  order.total;
  order.total === 3;
  return order.total;
}
""",
            "app.py": "def run(order):\n    order.total\n    order.total == 3\n    return 1\n",
        },
    )
    discarded = DeclarationReader(rule_id="ALL-CONT0002", family=SyntaxFact)

    oracle = Oracle.of("eslint", "no-unused-expressions").report(root)
    assert oracle.states(Site.at(_MODULE, 2), Site.at(_MODULE, 3))
    reached = Site(path="app.py", line=1, through=4)
    python = discarded.model_copy(update={"languages": ("python",)})
    assert python.report(root).states(reached, reached)
    differ(
        discarded.model_copy(update={"languages": ("typescript",)}).report(root),
        Relation.EQUALS,
        oracle,
        because="a bare member and comparison compute values and discard them in both readers",
    )


def test_the_restricted_import_claim_has_no_oracle_to_be_checked_against(
    tmp_path: Path,
) -> None:
    """`no-restricted-imports` reports nothing until somebody names what is restricted.

    MCMR adapts `typescript-eslint no-restricted-imports` into a measurement of how far a relative
    import climbs. The two are not the same question. ESLint asks whether an import matches a list
    a project wrote and answers nothing without one, while MCMR needs no configured list. This
    pins that deliberate difference so the adapted relationship cannot drift back into a native
    coverage claim.
    """
    root = written(
        tmp_path,
        {
            "src/deep/nested/leaf.ts": """import { helper } from '../../../shared/helper';
export const value = helper;
""",
            "src/shared/helper.ts": "export const helper = 1;\n",
        },
    )
    ours = FindingReader(
        rule_id="TS-MODU0002", family=ModuleSurfaceFact, suffixes=(".ts",)
    ).report(root)

    assert Oracle.of("eslint", "@typescript-eslint/no-restricted-imports").report(root).states()
    assert ours.states(Site.at("src/deep/nested/leaf.ts", 1))
