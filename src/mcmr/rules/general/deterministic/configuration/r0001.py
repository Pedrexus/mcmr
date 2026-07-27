import re

from ..... import rule
from .....facts import ProjectConfigurationFact
from .....models import Count


@rule
def hardcoded_path_policy_count(
    subject: ProjectConfigurationFact,
    *,
    minimum_paths: int = 3,
    policy_names: tuple[str, ...] = (
        "directories",
        "directory",
        "exclude",
        "excluded",
        "ignore",
        "ignored",
        "suffixes",
        "suffix",
    ),
) -> Count:
    """Count hardcoded path-discovery policies in Python collections.

    Definition
    ----------
    Inspect simple assignments to names whose normalized words include `exclude`, `excluded`,
    `ignore`, `ignored`, `directory`, `directories`, `suffix`, or `suffixes`. Report only list,
    tuple, and set literals containing at least three strings. Directory collections may contain
    safe path components. Suffix collections must contain dotted suffixes or suffix globs. Other
    policy names require at least one explicit separator, glob, hidden-name, or suffix marker.

    Evidence
    --------
    Each finding locates the complete assignment, records the number of literal paths, and retains
    up to 32 exact entries. The result counts assignments rather than individual strings. The value
    is the number of qualifying assignments rather than the number of paths they hold.

    Exceptions
    ----------
    One or two local paths, computed collections, URLs, mixed nonstring literals, arbitrary names,
    and generic exclusion lists without any path syntax abstain. Fields on Pydantic model classes
    whose names end in `Configuration` are already typed policy and also abstain. Small
    algorithm-owned suffix tables can configure a higher threshold or disable the rule. No
    automatic migration is offered because repository ignores and application configuration have
    different ownership. `minimum_paths` is how many literal entries a collection needs before it
    reads as a policy rather than a local list, and `policy_names` is the vocabulary a name is
    matched against, so a project spelling its own policies differently states those words.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       excluded_directories = (".git", ".venv", "build", "dist")
       ignored_suffixes = (".pyc", ".so", ".egg-info")

    Good
    ~~~~
    .. code-block:: python

       from pathlib import Path

       ignored = GitIgnore.from_root(Path.cwd())
       policy = ProjectConfiguration.read("pyproject.toml")

    References
    ----------
    Cites "Git documentation", gitignore
    https://git-scm.com/docs/gitignore
    Cites "Python Packaging User Guide", tool table
    https://packaging.python.org/en/latest/specifications/pyproject-toml/#tool-table
    Cites "The Python Standard Library", tomllib
    https://docs.python.org/3.14/library/tomllib.html
    Cites "The Python Standard Library", pathlib
    https://docs.python.org/3.14/library/pathlib.html
    """
    count = 0
    for assignment in subject.assignments:
        words = set(re.findall(r"[a-z]+", assignment.name.casefold()))
        selected = words.intersection(policy_names)
        if (
            not selected
            or assignment.collection_kind == "other"
            or len(assignment.values) < minimum_paths
            or assignment.is_typed_configuration_field
        ):
            continue
        if selected.intersection({"suffix", "suffixes"}):
            qualifies = all(value.startswith(".") or "*" in value for value in assignment.values)
        elif selected.intersection({"directory", "directories"}):
            qualifies = True
        else:
            qualifies = any(
                "/" in value or "\\" in value or "*" in value or value.startswith(".")
                for value in assignment.values
            )
        count += qualifies
    return count
