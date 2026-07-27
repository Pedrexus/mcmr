from ..... import rule
from .....facts import RepositoryHistoryFact
from .....models import Count


@rule
def coupled_files_that_never_name_each_other(
    subject: RepositoryHistoryFact,
    *,
    minimum_shared_commits: int = 5,
    minimum_confidence: float = 0.5,
) -> Count:
    """Count file pairs that keep changing together with no import between them.

    Definition
    ----------
    Report a pair that arrived together in at least `minimum_shared_commits` focused commits, that
    reaches `minimum_confidence` of the rarer file's own commits, and where no import line in
    either file names the other. Confidence is the share that matters rather than the raw count,
    because a file touched three hundred times shares a commit with everything by accident while
    one touched eight times and always beside the same neighbor is telling us something.

    Two files that change together are coupled whether or not the code says so. Where an import
    explains it, the structure already reported it and every other family here can see it. Where
    nothing explains it, the dependency lives in an assumption two files share, and that is the
    one kind of coupling no import graph can find.

    Evidence
    --------
    Each finding names both files, how many commits carried both, and each file's own commit
    count. The value is the number of unexplained pairs.

    Exceptions
    ----------
    A pair involving a test is skipped, because a test changing with the code it exercises is the
    system working rather than a defect. A sweeping commit, meaning a reformat, a mass rename, or a
    dependency bump, never votes on a pair at all, since it would couple everything it touched to
    everything else. A pair the two files genuinely share through a third module is real coupling
    that this reports honestly, and the repair is usually to name the shared thing rather than to
    merge the two files.

    The import reading is lexical, so a repository where no coupled pair names any other is one
    where the reader found no imports it understands rather than one where every pair is hidden.
    That case reports nothing, the same guard a claim about unreached routes needs.

    Examples
    --------
    Bad
    ~~~
    A `serializer` and a `parser` that changed together in nine of the eleven commits either one
    saw, neither importing the other. They share a wire format that is written down nowhere, so
    every change to one silently owes a change to the other.

    Good
    ~~~~
    The same two files after the format moves into a schema both import. They still change
    together, the import now says why, and a reader who opens one is told about the other.

    References
    ----------
    Cites "Your Code as a Crime Scene", chapter 7, temporal coupling
    Cites "Software Design X-Rays", chapter 5, change coupling across architectural boundaries
    Cites "Detection of Logical Coupling Based on Product Release History", ICSM 1998
    https://ieeexplore.ieee.org/document/738508
    """
    tested = {record.path for record in subject.files if record.is_test}
    judged = [
        pair
        for pair in subject.pairs
        if not tested & {pair.left, pair.right}
        and pair.shared_commit_count >= minimum_shared_commits
        and pair.shared_commit_count
        >= minimum_confidence * min(pair.left_commit_count, pair.right_commit_count)
    ]
    if not any(pair.import_reference_count for pair in judged):
        return 0
    return sum(not pair.import_reference_count for pair in judged)
