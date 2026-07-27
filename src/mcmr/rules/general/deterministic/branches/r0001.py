from ..... import rule
from .....facts import BranchFact
from .....models import Count


@rule
def value_dispatch_candidate(subject: BranchFact, *, minimum_arms: int = 3) -> Count:
    """Count condition chains that only select behavior by one value.

    Definition
    ----------
    Report a chain of `minimum_arms` or more arms where every arm compares the same subject against
    a distinct literal and reads nothing else. Such a chain is a lookup written as control flow.
    Every new case edits the same function, which is exactly the change a dispatch table, a match
    over a closed type, or a registry avoids. The rule reports the chain, not the individual arms,
    because the chain is what gets replaced.

    Evidence
    --------
    Each finding records the chain range, the subject, every literal it tests, and whether a
    fallback arm exists. The value is the number of chains.

    Exceptions
    ----------
    A chain whose arms test different subjects, compare with anything other than equality, or read
    additional state is real branching logic and is not counted. A chain of two arms is left alone
    because a table costs more than it saves at that size.

    Examples
    --------
    Three arms testing `kind == "pbs"`, `kind == "slurm"`, and `kind == "ssh"`, with or without a
    fallback beneath them, return `1` and should become a registry or a mapping. A chain testing
    `kind == "pbs"` and then `queue.is_full` returns `0`, because its second arm reads something
    else. A chain testing `kind == "pbs"` twice returns `0` as well, since two arms share one
    literal.

    References
    ----------
    Cites "Refactoring", replace conditional with polymorphism
    Cites Clippy match_like_matches_macro
    Cites Clippy comparison_chain
    https://rust-lang.github.io/rust-clippy/master/index.html#comparison_chain
    Cites "The Python Standard Library", `functools.singledispatch` and structural pattern matching
    https://docs.python.org/3/library/functools.html#functools.singledispatch
    """
    return sum(
        len(chain.arms) >= minimum_arms
        and bool(chain.subject)
        and all(arm.reads_subject_only and arm.literal for arm in chain.arms)
        and len({arm.literal for arm in chain.arms}) == len(chain.arms)
        for chain in subject.chains
    )
