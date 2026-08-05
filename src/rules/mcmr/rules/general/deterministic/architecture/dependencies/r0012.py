import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ModuleCouplingFact, Ratio
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ...coupling import CouplingRelations, PackageCoupling, counted_text, percentage_text


@rule("ALL-ARCH0003")
def dependency_on_a_less_stable_module(
    subject: Table[ModuleCouplingFact],
    *,
    tolerance: Ratio = 0.0,
) -> CountQuery:
    """Count package dependencies that point toward something less stable.

    Definition
    ----------
    Stability here is not a guess about how often a file changes, it is counted. A package that
    five others import and that imports one itself is hard to change, because five callers feel it,
    and Martin writes that as instability `I = Ce / (Ca + Ce)`, which is zero when nothing can push
    a change into the module and one when everything can. The Stable Dependencies Principle says an
    arrow must point toward stability, so an import from a package with a low `I` to a package with
    a higher one is reported, and `tolerance` is the slack a project allows before a difference
    counts.

    This is a layering violation found without anybody naming a layer. A written contract in a
    configuration file states which package may import which, and it rots the first time somebody
    adds a legitimate edge and widens the rule to keep the build green, until the file describes
    the code instead of constraining it. The dependency graph already says which modules the
    repository leans on, so the constraint can be derived every run and cannot drift away from what
    the code does.

    Evidence
    --------
    Each finding names the importing package, the imported package, the instability of both as a
    percentage, and how many packages depend on the importer, which is what says how far a change
    travels. The repair is a choice between inverting the arrow and moving what the two share, and
    both are decisions somebody has to make. The value is the number of this package's imports that
    point the wrong way.

    Exceptions
    ----------
    Only imports between packages this repository owns are read, since a third-party package has no
    instability inside this architecture. Imports within one package do not cross a component
    boundary and cannot violate the component principle. Declarative imports in Python
    `__init__.py` and Rust `mod.rs` files state a package's public ownership surface, so they stay
    out of implementation arrows between the facade and its children. Test code necessarily points
    at production code, so those verification arrows are not production component dependencies and
    stay out, while dependencies among test packages are still judged. A package in an import
    cycle is stable and unstable at once, and the two sides each report the other, so
    `ALL-ARCH0002` is the rule to fix first and this one settles afterward. A plugin a framework
    loads by name is imported by nothing static, so it reads as maximally unstable and its
    dependencies are judged accordingly, which is correct rather than a false positive.

    Examples
    --------
    Bad
    ~~~
    `codec.py` is imported by eight modules and imports two, so `I` is `0.2`. It imports `cli.py`,
    which imports six modules and is imported by none, so `I` is `1.0`. Every edit to the command
    line can now reach the codec, and through it the eight modules that depend on the codec. This
    returns `1`.

    Good
    ~~~~
    `cli.py` imports `codec.py`. The arrow runs from the volatile module to the settled one, so a
    change to the command line reaches nothing and a change to the codec is a decision somebody
    made deliberately. This returns `0`.

    References
    ----------
    Cites "Agile Software Development", the Stable Dependencies Principle
    Cites "Clean Architecture", chapter 14, component coupling
    Cites "Design Principles and Design Patterns"
    https://web.archive.org/web/20150906155800/http://www.objectmentor.com/resources/articles/Principles_and_Patterns.pdf
    Cites "JDepend", the tool that first computed these metrics over a package graph
    https://github.com/clarkware/jdepend
    """
    relations = PackageCoupling(CouplingRelations(subject))
    selected = relations.dependencies().filter(
        pl.col("dependency_instability") > pl.col("instability") + tolerance
    )
    frame = relations.counted(selected)
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("`"),
            pl.col("module"),
            pl.lit("` sits at "),
            percentage_text(pl.col("instability")),
            pl.lit(" percent instability and imports `"),
            pl.col("dependency_module"),
            pl.lit("` at "),
            percentage_text(pl.col("dependency_instability")),
            pl.lit(" percent instability, so every change to the second one reaches the "),
            counted_text(pl.col("afferent_count"), "package"),
            pl.lit(" that depend on the first"),
        ),
        (
            (
                "instability of the importer",
                pl.col("instability") * 100.0,
                Unit.PERCENTAGE,
            ),
            (
                "instability of the imported",
                pl.col("dependency_instability") * 100.0,
                Unit.PERCENTAGE,
            ),
            ("packages depending on the importer", pl.col("afferent_count"), Unit.COUNT),
        ),
        finding_order=pl.col("ordinal"),
        question=pl.concat_str(
            pl.lit("turn the arrow from `"),
            pl.col("module"),
            pl.lit("` to `"),
            pl.col("dependency_module"),
            pl.lit("` around"),
        ),
        options=(
            "invert it through a contract the settled module owns",
            "move what they share into a module both can depend on",
        ),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
