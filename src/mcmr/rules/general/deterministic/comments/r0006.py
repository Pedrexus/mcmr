import re

from ..... import rule
from .....facts import CommentFact
from .....models import Count

# A marker counts only where a comment opens, so a marker named in the middle of a sentence is
# prose about the work and a marker opening a comment at the end of a code line is the note
# itself. Every language MCMR reads opens a comment with one of these, so one reader serves all.
OPENED = re.compile(r"(?:#|//|/\*|\*|--|;)[ \t]*([A-Za-z]+)")


@rule
def unresolved_work_marker(
    subject: CommentFact,
    *,
    markers: tuple[str, ...] = ("todo", "fixme", "xxx", "hack"),
) -> Count:
    """Count comments opening with a marker for work nobody has done.

    Definition
    ----------
    Read every comment the repository holds and report one whose first word is a marker such as
    `TODO`, `FIXME`, `XXX`, or `HACK`. The word has to open the comment, so a marker mentioned in
    the middle of a sentence is prose about the work rather than a note left in place of it. The
    value is the number of markers, and `markers` chooses which words count.

    A marker is a promise the compiler cannot keep. It survives every refactor, it outlives the
    person who wrote it, and it is invisible to the issue tracker where the same sentence would
    have been scheduled, assigned, and eventually closed.

    The reader is neutral. A comment opens with `#`, `//`, `/*`, `--`, or `;` depending on the
    language, and all of those are read here, so this answers for whichever languages the kernel
    fills the comment family for. That is Python today and every frontend the day each fills it.

    Evidence
    --------
    Each finding names the file and the comment group holding the marker. The value counts the
    markers rather than the comments, since one group can hold several.

    Exceptions
    ----------
    A marker inside a string or a docstring is not a comment and is not read. A project that
    tracks its debt in the source on purpose narrows `markers` or turns the rule off, which is a
    decision worth making once rather than a line worth ignoring forever.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       # TODO: handle the empty case
       def load(path):
           return read(path)  # FIXME: this loses the encoding

    Good
    ~~~~
    .. code-block:: python

       def load(path):
           # An empty file is a valid manifest, tracked as issue 412.
           return read(path)

    References
    ----------
    Generalizes Pylint W0511 fixme
    Generalizes Ruff FIX001 line-contains-fixme
    Generalizes Ruff FIX002 line-contains-todo
    Generalizes Ruff FIX003 line-contains-xxx
    Generalizes Ruff FIX004 line-contains-hack
    Cites "The Pragmatic Programmer", on leaving the campsite clean
    Cites "Refactoring", chapter 3, comments as a deodorant for bad code
    """
    wanted = {marker.casefold() for marker in markers}
    return sum(
        found.casefold() in wanted
        for group in subject.groups
        if group.node is not None
        for found in OPENED.findall(group.node.text)
    )
