import polars as pl

from ..... import rule
from .....domain.contracts import Unit
from .....facts import SymbolReachFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("PY-NAMI0002")
def attribute_visibility(subject: Table[SymbolReachFact]) -> CountQuery:
    """Count public methods proven to be private implementation details.

    Definition
    ----------
    Report a public Python method when every resolved reference comes from inside its declaring
    class. The owner must already be non-public, at least one owner reference must exist, no
    reference may come from another owner, and no unresolved reference with the same member name
    may remain anywhere in the repository.

    Evidence
    --------
    Each finding records owner, non-owner, and unresolved same-name usage counts. These three
    counts make the conclusion deterministic instead of asking a model to infer intent from a
    spelling. The value is the number of public methods whose complete repository usage proves
    that they are implementation details of a non-public owner.

    Exceptions
    ----------
    Decorated methods and every class participating in inheritance are excluded because framework
    and subclass contracts may call members without ordinary graph edges. A public owner is also
    excluded because downstream users outside the repository may depend on its methods. An unused
    method is left to dead-code analysis rather than renamed.

    Examples
    --------
    `_Parser.parse` called only by `_Parser.run` is reported and should become `_parse`.
    `Parser.parse` is not reported because `Parser` may be a public API. `_Parser.parse` is also
    left alone when `client.parse()` remains unresolved or a derived class participates.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "The Python Tutorial", private variables and class-local references
    https://docs.python.org/3/tutorial/classes.html#private-variables
    """
    facts = subject.facts()
    selected = (
        subject.records("declarations")
        .join(
            facts.select("fact_id", "language", "is_test_module", "evidence"),
            on="fact_id",
            how="left",
        )
        .filter(
            (pl.col("language") == "python")
            & ~pl.col("is_test_module")
            & (pl.col("kind") == "method")
            & ~pl.col("is_decorated")
            & (pl.col("visibility") == "public")
            & (pl.col("owner_visibility") != "public")
            & ~pl.col("owner_has_inheritance")
            & (pl.col("owner_references") > 0)
            & (pl.col("non_owner_references") == 0)
            & (pl.col("unresolved_name_references") == 0)
        )
    )
    frame = subject.counted(selected)
    located = selected.with_columns(
        pl.col("span.path").alias("path"),
        pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
        pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
        pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
        pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
    )
    findings = FindingQuery.build(
        located,
        pl.concat_str(
            pl.lit("`"),
            pl.col("qualname"),
            pl.lit("` is public although only its non-public owner reaches it"),
        ),
        (
            ("references from inside its owner", pl.col("owner_references"), Unit.COUNT),
            ("references from another owner", pl.col("non_owner_references"), Unit.COUNT),
            (
                "unresolved references with the same name",
                pl.col("unresolved_name_references"),
                Unit.COUNT,
            ),
        ),
        finding_order=pl.col("ordinal"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
