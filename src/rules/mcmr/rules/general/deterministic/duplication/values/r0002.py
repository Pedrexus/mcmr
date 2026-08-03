import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......facts import LiteralGroupFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("ALL-DUPL0002")
def repeated_semantic_string_literal(
    subject: Table[LiteralGroupFact],
    *,
    minimum_occurrences: NonNegativeInt = 3,
    minimum_files: NonNegativeInt = 2,
    minimum_length: NonNegativeInt = 12,
) -> CountQuery:
    """Find repeated string literals that occupy one exact semantic role.

    Definition
    ----------
    Group an exact string value only when every occurrence has the same resolved syntax role. The
    initial roles are a named keyword on the same alias-resolved callable and one side of the same
    binary equality comparison against the same dotted operand. Model constructors, Pydantic calls,
    and Pydantic serialization methods own their keyword vocabularies, so those strings are
    excluded. Report a group only when it reaches `minimum_occurrences`, `minimum_files`, and
    `minimum_length`. The default twelve-character floor avoids replacing short local vocabulary
    with an abstraction whose name is not clearer than the repeated value. The value is the number
    of qualified groups.

    Evidence
    --------
    Each finding cites every path and line, the exact role, occurrence and file counts, and the
    narrowest common directory as a candidate ownership boundary. That boundary can own a named
    domain value, enum, constrained type, or API policy. The rule proposes no automatic edit
    because choosing the representation and public owner requires domain knowledge.

    Exceptions
    ----------
    Ordinary assignments, return values, positional arguments, dictionary values, f-strings,
    docstrings, chained comparisons, dynamic call targets, and unequal roles are excluded.
    Comparisons against the interpreter-owned `__name__` module sentinel are excluded because their
    literal belongs to Python's execution protocol rather than a project-owned policy. Keyword
    values passed to a resolved standard-library module are excluded because that module owns the
    value vocabulary. Comparisons against standard-library module names follow the same rule. Model
    constructors and Pydantic calls are also excluded because values such as
    `model_validator(mode="after")` and `Field(alias="schema")` should stay visible at their
    declaration rather than become indirect constants. Calls to `model_dump` retain literal
    serialization modes for the same reason. Other third-party and project operations remain
    eligible because repeated choices there can still encode project policy. The repository's Git
    ignore files decide whether generated and vendored paths exist in this scan, and per-rule globs
    can narrow that source set further. Equal text in different keyword names, callables, compared
    operands, operators, or operand positions does not form one group. Short values remain local
    unless the project lowers `minimum_length` for a domain where a short token carries stable
    policy meaning.

    Examples
    --------
    Bad
    ~~~
    The same transport topic is repeated across independent modules with one stable role.

    .. code-block:: python

       transport.publish(topic="audit-events")
       transport.publish(topic="audit-events")
       transport.publish(topic="audit-events")

    Good
    ~~~~
    A domain-owned value makes the policy explicit, while unrelated human text remains local.

    .. code-block:: python

       transport.publish(topic=AuditTopic.EVENTS)
       logger.info("audit-events")
       field: str = Field(alias="schema")

    References
    ----------
    Cites "The Python Standard Library", `ast` for calls, keywords, comparisons, and constants
    https://docs.python.org/3/library/ast.html
    Cites "Refactoring", Replace Magic Literal
    https://refactoring.com/catalog/replaceMagicLiteral.html
    """
    relations = subject
    file_counts = (
        relations.values("string_groups.files")
        .group_by("parent_id", maintain_order=True)
        .agg(pl.col("string_value").n_unique().cast(pl.UInt64).alias("file_count"))
    )
    selected = (
        relations.records("string_groups")
        .join(file_counts, left_on="record_id", right_on="parent_id", how="left")
        .with_columns(pl.col("file_count").fill_null(0))
        .filter(
            ~pl.col("is_excluded_vocabulary")
            & (pl.col("value").str.len_chars() >= minimum_length)
            & (pl.col("occurrence_count") >= minimum_occurrences)
            & (pl.col("file_count") >= minimum_files)
        )
    )
    frame = relations.counted(selected)
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        pl.lit(1, dtype=pl.UInt64),
        findings=FindingQuery.precise_integer(
            frame,
            value,
            "repeated semantic string literal",
            evidence=pl.col("evidence"),
        ),
    )
