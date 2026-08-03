from pathlib import Path

from mcmr.accounting.upstream import ClaimIndex, Coverage, ToolCoverage
from mcmr.facts import (
    ImportBindingFact,
    SyntaxFact,
)

from ...oracle import (
    DeclarationReader,
    Oracle,
    Relation,
    Site,
    catalog,
    differ,
    written,
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
            "generated.py": """class Base:
    def run(self):
        return 1


class Engine(Base):
    def a(self):
        return super(type(self), self).run()

    def b(self):
        return super(self.__class__, self).run()

    def c(self):
        return super(Engine, self).run()

    def d(self):
        return super().run()

    def e(self):
        return super(Base, self).run()
"""
        },
    )
    oracle = Oracle.of("pylint", "bad-super-call").report(root)

    assert oracle.states(Site.at("generated.py", 8), Site.at("generated.py", 11))
    differ(
        DeclarationReader(rule_id="PY-CLAS0010", family=SyntaxFact).report(root),
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
            "generated.py": """class Base:
    def run(self):
        return 1


class Other:
    pass


class Engine(Base):
    def run(self):
        return super(Other, self).run()
"""
        },
    )
    oracle = Oracle.of("pylint", "bad-super-call").report(root)

    assert oracle.states(Site.at("generated.py", 12))
    differ(
        DeclarationReader(rule_id="PY-CLAS0010", family=SyntaxFact).report(root),
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
            "pkg/sub/module.py": """from . import third
from .. import fourth
from ... import fifth
""",
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
            "generated.py": """def render(template, title):
    prefix = title.upper()
    return template.format(**locals())


def echo(template, title):
    return template.format(title, **locals())


def clean(value):
    kept = value * 2
    return kept
"""
        },
    )
    oracle = Oracle.of("pylint", "possibly-unused-variable").report(root)
    ours = DeclarationReader(rule_id="ALL-FUNC0011", family=SyntaxFact).report(root)

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
        "unused-import": "oracle_upstream/oracle/test_unused.py",
        "protected-access": "oracle_upstream/oracle/test_style.py",
        "fixme": "oracle_upstream/oracle/test_style.py",
        "non-ascii-file-name": "oracle_upstream/oracle/test_style.py",
        "bad-super-call": "oracle_upstream/oracle/test_classes.py",
        "relative-beyond-top-level": "oracle_upstream/oracle/test_classes.py",
        "duplicate-code": "quality/test_clone_rules.py",
        "too-many-public-methods": "oracle_metrics/test_design_measure_oracle.py",
        "too-many-ancestors": "oracle_metrics/test_design_measure_oracle.py",
        "abstract-method": "classes/overrides/oracle/test_pylint.py",
        "arguments-differ": "classes/overrides/oracle/test_pylint.py",
        "arguments-renamed": "classes/overrides/oracle/test_pylint.py",
        "invalid-overridden-method": "classes/overrides/oracle/test_pylint.py",
        "method-hidden": "classes/overrides/oracle/test_pylint.py",
        "non-parent-init-called": "classes/overrides/oracle/test_pylint.py",
        "overridden-final-method": "classes/overrides/oracle/test_pylint.py",
        "signature-differs": "classes/overrides/oracle/test_pylint.py",
        "subclassed-final-class": "classes/overrides/oracle/test_pylint.py",
        "super-init-not-called": "classes/overrides/oracle/test_pylint.py",
    }
    definitions = list(catalog().definitions)
    account = ToolCoverage(tool="pylint", claims=ClaimIndex(definitions=definitions))
    native = {entry.rule.symbol for entry in account.entries if entry.coverage is Coverage.NATIVE}

    assert set(exercised) <= native
    for symbol, case in exercised.items():
        assert (Path(__file__).parents[2] / case).exists(), f"{symbol} names a case that is gone"
    assert native - set(exercised) == {
        "cyclic-import",
        "unused-private-member",
        "useless-parent-delegation",
    }, sorted(native - set(exercised))
