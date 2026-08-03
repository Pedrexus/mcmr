import polars as pl

from ..... import rule
from .....domain.contracts import FixSafety
from .....facts import FunctionFact
from .....query import FindingQuery, FixQuery, RuleQuery
from .....table import FunctionRelation, Table


@rule("PY-DEAD0001", fix_safety=FixSafety.REVIEW)
def unreferenced_private_function(subject: Table[FunctionFact]) -> RuleQuery[bool]:
    """Detect an undecorated private module function without project reference evidence.

    Definition
    ----------
    Inspect module functions with one leading underscore and no decorator. Retain a function when
    another source location loads its name, accesses an attribute with the same name, or contains
    that name as a string for dynamic lookup. A recursive reference inside the candidate does not
    make an otherwise unreachable function live. Dunder hooks, methods, classes, public API, and
    decorated registrations are outside the rule. Ruff continues to own unused imports and local
    variables.

    Evidence
    --------
    Each finding points to the definition and records the high-confidence private-function scope.
    The rule reuses the project AST prepared by the collector and performs no file read or second
    parse.

    Exceptions
    ----------
    Dynamic lookup assembled from multiple strings and external consumers outside the scanned
    project cannot be proved. The rule prefers a false negative when any plausible project
    reference exists. Public library functions are deliberately excluded because repository-only
    analysis cannot know their consumers.

    Examples
    --------
    Bad
    ~~~
    `def _obsolete(): ...` with no project reference produces one finding.

    Good
    ~~~~
    `_parse` passed as a callback, `module._parse()`, and `getattr(module, "_parse")` retain
    the function. `@router.register` and public functions are outside the candidate set.

    References
    ----------
    Generalizes Pylint W0238 unused-private-member
    Cites "Vulture documentation", unused function detection and confidence
    https://github.com/jendrikseipp/vulture
    Cites "PEP 8, Style Guide for Python Code", Public and Internal Interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    """
    decorators = (
        subject.lazy(FunctionRelation.DECORATORS)
        .group_by("function_id")
        .agg(pl.len().cast(pl.UInt64).alias("decorator_count"))
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(decorators, left_on="entity_id", right_on="function_id", how="left")
        .with_columns(pl.col("decorator_count").fill_null(0))
    )
    value = (
        (pl.col("scope") == "module")
        & (pl.col("visibility") != "public")
        & (pl.col("decorator_count") == 0)
        & (pl.col("reference_count") == pl.col("is_recursive").cast(pl.UInt64))
    )
    repairable = frame.filter(pl.col("definition_id").is_not_null())
    rewrites = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("remove").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("definition_id").alias("id"),
        pl.col("definition_path").alias("path"),
        pl.col("definition_start_line").alias("start_line"),
        pl.col("definition_start_column").alias("start_column"),
        pl.col("definition_end_line").alias("end_line"),
        pl.col("definition_end_column").alias("end_column"),
        pl.col("definition_kind").alias("kind"),
        pl.col("definition_text").alias("text"),
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "unreferenced private function"),
        fix=FixQuery.build(
            "Delete a nonpublic function nothing in its own module calls.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
