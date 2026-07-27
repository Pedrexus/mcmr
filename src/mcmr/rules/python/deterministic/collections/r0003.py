from ..... import rule
from .....facts import CollectionFact
from .....models import Count


@rule
def local_collection_representation_candidate(
    subject: CollectionFact,
    *,
    sequence_preference: str = "list",
    prefer_membership_set: bool = True,
) -> Count:
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
    return sum(
        collection.value_count >= 2
        and collection.has_homogeneous_literals
        and (
            collection.all_reads_are_iteration
            and collection.kind != sequence_preference
            or prefer_membership_set
            and collection.all_reads_are_membership
            and collection.values_are_unique
        )
        for collection in subject.local_collections
    )
