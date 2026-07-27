from ..... import rule
from .....facts import CommentFact
from .....models import Count, FixSafety, Remove, SourceRewrite


@rule
def commented_out_code(subject: CommentFact, *, minimum_lines: int = 1) -> Count:
    """Count comment groups that are source rather than prose.

    Definition
    ----------
    Report a contiguous comment group of at least `minimum_lines` lines whose text parses as source
    in the language of the file it lives in. Commented-out code is dead weight that reads as
    intent, since it survives refactors untouched, it is never compiled or tested, and every later
    reader has to decide whether it matters. Version control already keeps the old version.

    Evidence
    --------
    Each finding records the comment range and its measured size. The value is the number of such
    groups.

    Exceptions
    ----------
    A tool directive, such as a suppression or a formatting marker, is excluded even when it
    parses.
    A documentation example inside a comment often parses too, so a project that keeps examples in
    comments should raise `minimum_lines` or exclude those paths. Prose that happens to parse, such
    as a single bare word, is why the default counts a group rather than a line.

    Examples
    --------
    Three commented lines that reconstruct a former loop return `1`. A comment reading `# retry
    twice before giving up` returns `0`, and so does a suppression directive.

    References
    ----------
    Generalizes SonarSource S125
    https://rules.sonarsource.com/python/RSPEC-S125/
    Cites "Clean Code", chapter on comments
    Cites "The Pragmatic Programmer", on commented-out code
    """
    return sum(
        group.parses_as_source and not group.is_directive and group.line_count >= minimum_lines
        for group in subject.groups
    )


@commented_out_code.fix(is_default=True, safety=FixSafety.REVIEW)
def remove_commented_out_code(
    subject: CommentFact, *, minimum_lines: int = 1
) -> list[SourceRewrite]:
    """Delete each run of commented lines that is source rather than prose."""
    return [
        Remove(target=group.node)
        for group in subject.groups
        if group.node is not None
        and group.parses_as_source
        and not group.is_directive
        and group.line_count >= minimum_lines
    ]
