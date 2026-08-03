import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import CallRelation, Table


@rule("PY-CLAS0008")
def direct_method_descriptor_call_count(subject: Table[CallFact]) -> CountQuery:
    """Count `staticmethod` and `classmethod` calls used without decorator syntax.

    Definition
    ----------
    Parse one Python source file and count direct calls to the built-in `staticmethod` or
    `classmethod` descriptor constructors. This includes their explicit `builtins` forms. Method
    binding policy should be visible next to the method declaration through `@staticmethod` or
    `@classmethod`, not reconstructed through assignment or a class-body alias.

    Evidence
    --------
    Each finding identifies the complete call range and the descriptor constructor that was
    invoked. A bare decorator is an AST decorator name rather than a call, so normal decorator
    syntax cannot trigger this rule. The value is the number of direct descriptor constructor
    calls.

    Exceptions
    ----------
    Python permits direct descriptor construction, so this is an explicit readability policy
    rather than a language error. Calls through dynamic aliases are not guessed. Projects that
    intentionally build descriptors or metaclasses dynamically can disable this rule for that
    narrow source boundary.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       class Parser:
           parse = staticmethod(parse)

       wrapped = classmethod(build)

    Good
    ~~~~
    .. code-block:: python

       class Parser:
           @staticmethod
           def parse(text: str) -> "Parser":
               return Parser(text)

           @classmethod
           def build(cls, text: str) -> "Parser":
               return cls(text)

    References
    ----------
    Cites "The Python Standard Library", staticmethod
    https://docs.python.org/3/library/functions.html#staticmethod
    Cites "The Python Standard Library", classmethod
    https://docs.python.org/3/library/functions.html#classmethod
    Cites "Python HOWTOs", descriptor guide
    https://docs.python.org/3/howto/descriptor.html#static-methods-and-class-methods
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .filter(
            pl.col("qualified_name").is_in(["builtins.staticmethod", "builtins.classmethod"])
            & ~pl.col("is_decorator_factory")
        )
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "qualified_name",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("qualified_name"),
                pl.lit("` constructs a descriptor directly instead of using decorator syntax"),
            ),
            (("direct method descriptor call count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
