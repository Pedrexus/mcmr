from ..... import rule
from .....facts import DirectoryFact


@rule
def empty_directories(
    subject: DirectoryFact,
) -> bool:
    """Detect empty directories after configured exclusions.

    Definition
    ----------
    Report a directory the repository walk met that holds no visible entry. An entry is visible
    when the exclusion set keeps it and its name does not begin with a dot, and files and
    subdirectories both count, so a folder holding only a cache nobody scans still reads as empty.
    An empty directory is a decision nobody finished, either a package that was emptied without
    being deleted or a placeholder whose reason nobody wrote down, and every reader who meets it
    has to work out which.

    The provider walks the tree rather than deriving directories from the files it parsed, which is
    the only way a directory holding no source can be seen at all. Version control stores files
    rather than folders, so an empty directory in a checkout is either a leftover somebody has to
    decide about or a placeholder that says so in its own name, and `is_retained` tells the two
    apart.

    Evidence
    --------
    Each finding names one repository-relative directory holding nothing visible, together with the
    count of entries it does hold and the ignore and retention decisions the walk made about it.
    The result reports whether this directory is empty after the exclusions.

    Exceptions
    ----------
    A directory the exclusion set removes is never scanned and its subtree is never entered, so a
    checked-out build tree, a cache, and an environment never reach this rule at all. A dotted
    directory is scanned for the source it holds but arrives with `is_ignored` set, since a leading
    dot is how this platform spells machinery rather than layout, and what sits inside one is not
    described at all.

    A directory a project retains on purpose is recognized by the placeholder inside it rather than
    by a list of paths, which is what keeps the exemption from going stale the moment a folder
    moves.

    Examples
    --------
    An empty `src/unused` directory that nothing ignores or retains returns `true`, and so does a
    `logs` directory holding only the `__pycache__` the exclusion set removes. An empty
    `.pytest_cache` returns `false` because a dotted name is machinery, a `fixtures` directory
    holding one `.gitkeep` returns `false` because that placeholder retains it, and a
    `tests/fixtures` directory holding one file returns `false` as well.

    References
    ----------
    Cites "Git documentation", gitignore patterns
    https://git-scm.com/docs/gitignore
    """
    return subject.visible_entry_count == 0 and not subject.is_ignored and not subject.is_retained
