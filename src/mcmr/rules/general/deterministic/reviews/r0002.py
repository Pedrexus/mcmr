from ..... import rule
from .....facts import ChangeFact
from .....models import Percentage


@rule
def review_coverage(
    subject: ChangeFact,
) -> Percentage:
    """Measure independently reviewed changes on protected development lines.

    Definition
    ----------
    Divide in-scope nontrivial changes approved by an eligible reviewer other than the author by
    all in-scope nontrivial changes and return the percentage.

    Evidence
    --------
    Findings retain change identity, author, reviewers, ownership, approval, and merge path. The
    value is the percentage of in-scope changes approved by an eligible reviewer other than the
    author.

    Exceptions
    ----------
    Emergency changes may follow a documented retrospective review path. Mechanical bot changes
    may use separate verification policy.

    Examples
    --------
    Ninety-five independently reviewed changes among one hundred produce `95`. Self-approval does
    not satisfy independent review.

    References
    ----------
    Cites "Software Engineering at Google", Code Review
    Cites "OpenSSF Scorecard", branch protection checks
    """
    return subject.changes.coverage(
        "nontrivial", "approved", "eligible_reviewer", "reviewer_is_not_author"
    )
