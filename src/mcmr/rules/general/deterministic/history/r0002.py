from ..... import rule
from .....facts import RepositoryHistoryFact
from .....models import Count


@rule
def file_too_many_hands_have_touched(
    subject: RepositoryHistoryFact,
    *,
    minimum_authors: int = 4,
    minimum_commits: int = 5,
) -> Count:
    """Count files spread across so many authors that nobody can answer for them.

    Definition
    ----------
    Report a file at least `minimum_authors` distinct people changed across at least
    `minimum_commits` commits. A file one person keeps has a reader who knows why every line is
    there. A file eight people have each visited twice has none, and the next question about it
    goes unanswered or gets answered wrongly. Structure cannot see this at all, because the code
    reads exactly the same whoever wrote it.

    The commit floor is what keeps the measure about spread rather than about age. A file six
    people touched in six commits is genuinely shared, while one that three people touched once
    each during a repository wide rename never had an owner to lose.

    Evidence
    --------
    Each finding names the file, how many distinct authors changed it, and how many commits they
    changed it in. The value is the number of files above both floors.

    Exceptions
    ----------
    A manifest, a changelog, and a dependency lock are meant to be edited by everyone and say
    nothing about ownership, so a project keeping them under this scan raises the floors or
    excludes them. A repository with fewer contributors than `minimum_authors` reports nothing,
    which is the correct answer rather than a miss. A long lived project loses authors to time, so
    a narrower history window measures who owns it now instead of who ever did.

    Examples
    --------
    Bad
    ~~~
    A `settings` module that nine people changed across forty commits. Each of them added the one
    option their feature needed, nobody removed anything, and no one can now say which options are
    still read.

    Good
    ~~~~
    A `settings` module that one person changed across forty commits. It is just as busy, and
    there is somebody who can say what every option is for.

    References
    ----------
    Cites "Software Design X-Rays", chapter 7, knowledge distribution and off-boarding risk
    Cites "Your Code as a Crime Scene", chapter 9, code as a crime scene of many hands
    Cites "Don't Touch My Code", FSE 2011
    https://dl.acm.org/doi/10.1145/2025113.2025119
    """
    return sum(
        record.author_count >= minimum_authors and record.commit_count >= minimum_commits
        for record in subject.files
    )
