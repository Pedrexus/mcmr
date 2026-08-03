import polars as pl

from ...... import rule
from ......facts import CollectionFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("PY-COLL0003")
def local_collection_representation_candidate(
    subject: Table[CollectionFact],
    *,
    sequence_preference: str = "list",
    prefer_membership_set: bool = True,
) -> CountQuery:
    """Recommend list, tuple, or set only when local use proves interchangeability.

    Definition
    ----------
    Inspect unannotated local list and tuple literals containing at least two literal values of one
    kind. The candidate is a name one callable binds exactly once, so every read of it is inside
    that callable and can be counted. If every read is the iterable of a loop or a comprehension,
    recommend the configured sequence form, which defaults to `list`. If every read is a membership
    test and the values are distinct, recommend `set` when enabled. One read that is neither leaves
    both claims unproven and the rule abstains.

    Evidence
    --------
    Each finding names the local binding, the form it is written as, how many values it holds, and
    which of the two proofs its reads satisfy. The rule reports a candidate without a fix because
    public annotations and downstream behavior can still impose a contract outside the function.
    The value is the number of local collections whose proven use fixes a clearer representation.

    Exceptions
    ----------
    Annotated values, module constants, returned values, escaped arguments, indexing, unpacking,
    equality, mutation, duplicate membership values, heterogeneous tuples, hash keys, and unknown
    uses are excluded, and so is a name the callable rebinds, since the second binding may hold
    anything. Fixed heterogeneous records remain tuples. Frozen snapshots and hashable keys remain
    tuples or frozen sets even when the project generally prefers lists. `sequence_preference` is
    the form an iteration-only literal is recommended as, defaulting to a list, and setting
    `prefer_membership_set` to false leaves a membership-only literal alone for a project that
    would rather keep its order.

    Examples
    --------
    Bad
    ~~~
    A local `formats = ("json", "toml")` a loop is the only reader of is reported as a list
    candidate under the default preference. A list of distinct values read only by
    `value in formats` is a set candidate.

    Good
    ~~~~
    A coordinate tuple unpacked into `x, y`, a tuple used as a dictionary key, an ordered list that
    is indexed, a mixed `("json", 2)`, and a frozen return snapshot retain their representation. A
    literal that is looped over once and indexed once is left alone as well, since indexing is a
    read the recommended form would not answer.

    References
    ----------
    Cites "Fluent Python", chapter 2, sequences
    Cites "The Python Tutorial", data structures
    https://docs.python.org/3/tutorial/datastructures.html
    Cites "The Python Language Reference", standard type hierarchy
    https://docs.python.org/3/library/stdtypes.html
    """
    relations = subject
    selected = relations.records("local_collections").filter(
        (pl.col("value_count") >= 2)
        & pl.col("has_homogeneous_literals")
        & (
            (pl.col("all_reads_are_iteration") & (pl.col("kind") != sequence_preference))
            | (
                pl.lit(prefer_membership_set)
                & pl.col("all_reads_are_membership")
                & pl.col("values_are_unique")
            )
        )
    )
    frame = relations.counted(selected)
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(
            frame,
            value,
            "local collection representation candidate",
            evidence=pl.col("evidence"),
        ),
    )
