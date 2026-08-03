import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import ModuleFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import GenericRelation, Table


@rule("ALL-MODU0001", policy=Numeric(maximum=500))
def module_line_count(
    subject: Table[ModuleFact],
) -> CountQuery:
    """Measure how many physical lines one module holds.

    Definition
    ----------
    Count every physical line of this source file, including comments, docstrings, and blank lines.
    Length is what a reader pays before understanding anything, and counting the lines as written
    is the only count that matches what they scroll through.

    The measurement stops at the number. A separate policy compares it against a ceiling a project
    chose, such as four hundred lines, because a generated schema and a hand-written service
    tolerate very different lengths and only the project knows which one this is.

    Evidence
    --------
    The finding names the module, its exact physical line count, and how many classes and
    functions that length is spent on, which is what says whether a long module is one large
    subject or several small ones sharing a file. The repair is a choice, since splitting by line
    count alone produces fragments nobody can name. The value is the physical line count.

    Exceptions
    ----------
    A generated file, a vendored dependency, a schema-heavy module, and a migration are long for
    reasons nobody is going to fix, so a project excludes them or judges them under a separate
    policy. Splitting a long module into arbitrary fragments, inheritance layers, or forwarding
    files makes the count smaller and the codebase worse, so a repair is worth checking against
    cohesion. Pylint `C0302` measures the same thing, so a project already running it with the same
    ceiling should disable one of the two.

    Examples
    --------
    A four-hundred-and-one-line module returns `401` and a three-hundred-and-fifty-line one returns
    `350`. Neither value is a failure by itself, since the configured policy is what decides which
    lengths this project accepts.

    References
    ----------
    Cites Pylint C0302 too-many-lines
    https://pylint.readthedocs.io/en/latest/user_guide/messages/convention/too-many-lines.html
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    facts = subject.lazy(GenericRelation.FACTS)
    lines = pl.col("physical_line_count")
    classes = pl.col("class_count")
    functions = pl.col("function_count")
    findings = FindingQuery.build(
        facts,
        pl.concat_str(
            pl.lit("`"),
            pl.col("path"),
            pl.lit("` runs "),
            lines,
            pl.when(lines == 1).then(pl.lit(" line")).otherwise(pl.lit(" lines")),
            pl.lit(" holding "),
            classes,
            pl.when(classes == 1).then(pl.lit(" class")).otherwise(pl.lit(" classes")),
            pl.lit(" and "),
            functions,
            pl.when(functions == 1).then(pl.lit(" function")).otherwise(pl.lit(" functions")),
        ),
        (
            ("physical lines", lines, Unit.COUNT),
            ("classes", classes, Unit.COUNT),
            ("functions", functions, Unit.COUNT),
        ),
        question=pl.concat_str(
            pl.lit("split `"),
            pl.col("path"),
            pl.lit("` along a seam a reader can name"),
        ),
        options=(
            "move one whole subject into its own module",
            "accept the length where the module is one subject",
        ),
    )
    return RuleQuery.integer(facts, lines, findings=findings)
