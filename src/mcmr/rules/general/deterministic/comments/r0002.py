from pydantic import PositiveInt, validate_call

from ..... import rule
from .....facts import CommentFact, CommentGroup
from .....models import Percentage


def is_a_legal_notice(group: CommentGroup, markers: tuple[str, ...]) -> bool:
    """Whether one comment group states a licence rather than anything about this code.

    A notice is the same words in every file of a project, copied there by policy and identical
    whatever the file does, so measuring it says how long the licence is and nothing about how
    much this file explains itself.
    """
    written = group.node.text.lower() if group.node is not None else ""
    return any(marker in written for marker in markers)


@rule
@validate_call
def comment_length(
    subject: CommentFact,
    *,
    measure: str = "tokens",
    normalization_max: PositiveInt = 200,
    notice_markers: tuple[str, ...] = (
        "spdx-license-identifier",
        "copyright",
        "licensed under",
        "all rights reserved",
    ),
) -> Percentage:
    """Normalize the longest contiguous comment without judging its usefulness.

    Definition
    ----------
    Consecutive comment lines form one group, `measure` chooses what a group's size is counted in,
    and the largest group in the file that is not a legal notice is the one measured. That raw size
    is divided by `normalization_max` and stated as a percentage, so a group at or past the
    normalization maximum reads as one hundred and everything shorter scales beneath it.

    A licence is left out because it is not a comment about this code. It is the same words in
    every file of the project, put there by policy, and the fifteen-line notice one library opens
    all of its two hundred and six files with made this rule fail every one of them, which tells a
    reader nothing at all. `notice_markers` names what a notice opens with, so a project spelling
    one differently configures it rather than turning the rule off.

    The normalization is what makes the number comparable. A raw token count means nothing across
    two repositories with different comment habits, and a share of an agreed ceiling means the same
    thing in both. The rule states the share and a project policy decides which share is too much,
    since a protocol citation and a restated line of code are the same length and worth very
    different things.

    Evidence
    --------
    The finding names the file and the range of the largest comment group it measured together with
    its raw size in the selected measure. The value is that size as a percentage of
    `normalization_max`, clipped at one hundred.

    Exceptions
    ----------
    A file with no comment at all measures zero rather than being skipped, which keeps the value
    comparable across a repository, and so does a file holding nothing but its licence. Nothing
    here judges whether a long comment is worth its length, so a rationale, a safety note, and a
    protocol citation all measure exactly as long as they are, and the contextual comment rules are
    what say whether they earn it.

    Examples
    --------
    A forty-token group under the default two-hundred-token normalization maximum returns `20`. A
    two-hundred-and-fifty-token group returns `100`, since the value is clipped rather than allowed
    past the ceiling. A file whose longest run of comment lines is a single line returns close to
    zero, and one opening with a fifteen-line Apache notice and saying nothing else returns `0`.

    References
    ----------
    Cites "Clean Code", chapter 4
    Cites "A Philosophy of Software Design", chapters 12 through 15
    """
    largest = max(
        (
            group.size(measure)
            for group in subject.groups
            if not is_a_legal_notice(group, notice_markers)
        ),
        default=0,
    )
    return min(largest / normalization_max * 100.0, 100.0)
