from ..... import rule
from .....facts import CollectionFact
from .....models import Count


@rule
def literal_pair_sequence_mapping_candidate(subject: CollectionFact) -> Count:
    """Count fixed pair sequences whose complete use has unique-key mapping semantics.

    Definition
    ----------
    Inspect names one callable body initializes with a list or tuple literal holding at least two
    two-tuples. Require every key to be a unique literal of one exact supported kind. Require the
    name to have one assignment and every read to be the iterable of a lookup loop that unpacks
    `key, value`, compares the key exactly once, and directly returns the matching value. The
    result is the number of sequences for which a dictionary states the observed contract more
    clearly.

    Evidence
    --------
    Each finding identifies the fixed table, proven unique key count, and every lookup-loop line.
    No automatic fix is offered because callers, public annotations, and missing-key behavior may
    require a coordinated refactor even when the local data structure is unambiguous. The value is
    the number of pair sequences a dictionary would state more clearly.

    Exceptions
    ----------
    Preserve sequences when keys repeat, key expressions are dynamic, key kinds mix, order is read,
    pairs escape, the sequence is returned, a loop consumes whole pairs, or any use has effects
    beyond exact lookup. A module constant is never a candidate, because its readers are every file
    that imports it and the file declaring it cannot see them. A sequence supplied by a caller is
    not assumed unique from its annotation. Ruff `C406` continues to own literal sequences passed
    directly to `dict`, while Ruff `SIM116` owns repeated `if` return tables. This rule covers
    neither form.

    Examples
    --------
    Bad
    ~~~
    `rows = [("open", True), ("closed", False)]` followed only by loops that return the value for
    a matching key behaves as a dictionary and is reported.

    Good
    ~~~~
    Repeated keys, ordered priority rules, a returned pair list, and a loop that processes every
    pair remain sequences. A literal passed directly to `dict` remains Ruff's diagnostic.

    References
    ----------
    Cites "The Python Language Reference", mapping types
    https://docs.python.org/3/library/stdtypes.html#mapping-types-dict
    Cites "The Python Language Reference", dictionary displays
    https://docs.python.org/3/reference/expressions.html#dictionary-displays
    Cites Ruff C406 unnecessary-literal-dict
    https://docs.astral.sh/ruff/rules/unnecessary-literal-dict/
    Cites Ruff SIM116 if-else-block-instead-of-dict-lookup
    https://docs.astral.sh/ruff/rules/if-else-block-instead-of-dict-lookup/
    """
    return sum(
        sequence.pair_count >= 2
        and sequence.keys_are_unique_literals
        and sequence.has_single_assignment
        and sequence.all_reads_are_lookup_loops
        for sequence in subject.pair_sequences
    )
