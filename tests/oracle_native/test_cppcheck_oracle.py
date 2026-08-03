from typing import TYPE_CHECKING

from mcmr.facts import SymbolReachFact, SyntaxFact

from ..oracle import (
    DeclarationReader,
    Oracle,
    Relation,
    Site,
    differ,
    needs,
    needs_kernel,
    written,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [needs_kernel, needs("cppcheck")]

# MCMR makes no Cppcheck claim yet. These shared questions are measured so any future claim starts
# from evidence rather than hope.
_CONST_STATEMENT = "constStatement"
_UNUSED_FUNCTION = "unusedFunction"


def test_statement_without_effect_agrees_with_cppcheck(tmp_path: Path) -> None:
    """`constStatement` reports the discarded value this rule reports, in the same callable.

    Cppcheck names the line and `ALL-CONT0002` answers for the whole declaration, so the line is
    folded into the callable holding it and a finding attributed to the wrong function fails even
    where the totals agree. The second callable is what makes the selection real: a value handed to
    a call is not a discarded one, and neither reader says it is.
    """
    root = written(
        tmp_path,
        {
            "unit.cpp": """int discard(int value) {
  value;
  return value + 1;
}

int keep(int value) {
  int total = value;
  return total;
}
"""
        },
    )
    oracle = Oracle.of("cppcheck", _CONST_STATEMENT).report(root)

    assert oracle.states(Site.at("unit.cpp", 2))
    differ(
        DeclarationReader(rule_id="ALL-CONT0002", family=SyntaxFact, languages=("cpp",)).report(
            root
        ),
        Relation.EQUALS,
        oracle,
        because="a statement whose whole content only produces a value does nothing to either",
    )


def test_unreferenced_declaration_agrees_with_cppcheck_on_what_nothing_reaches(
    tmp_path: Path,
) -> None:
    """`unusedFunction` answers what `ALL-REAC0001` answers, and MCMR claims none of it today.

    One thing parts the readers here and it is a location boundary. `SymbolReach`
    carries no span of its own, so MCMR locates this finding at the module while Cppcheck locates
    it at the declaration, and the two coincide only where a file declares its callable first.

    `caller` calls `beta` in the same file, and both readers credit that call and stay quiet about
    `beta`. The Python twin states the same relationship, which proves both graph frontends answer
    the shared reach rule from the same primitive evidence.
    """
    root = written(
        tmp_path,
        {
            "alpha.cpp": "int alpha(int value) {\n  int total = value;\n  return total + 1;\n}\n",
            "beta.cpp": """int beta(int value) {
  int total = value;
  return total + 2;
}

int caller(int value) {
  return beta(value);
}
""",
            "twin.py": """def beta(value):
    return value + 2


def caller(value):
    return beta(value)
""",
        },
    )
    oracle = Oracle.of("cppcheck", _UNUSED_FUNCTION).report(root)
    rule = DeclarationReader(rule_id="ALL-REAC0001", family=SymbolReachFact)

    assert oracle.states(Site.at("alpha.cpp", 1), Site.at("beta.cpp", 6))
    differ(
        rule.model_copy(update={"languages": ("cpp",)}).report(root),
        Relation.EQUALS,
        oracle.minus(Site.at("beta.cpp", 6)).plus(Site.at("beta.cpp", 1)),
        because=(
            "both find only alpha and caller after cppcheck's declaration site is folded to "
            "the module"
        ),
    )
    assert (
        rule.model_copy(update={"languages": ("python",)})
        .report(root)
        .states(Site.at("twin.py", 1))
    )
