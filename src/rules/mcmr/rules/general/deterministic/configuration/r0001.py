import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....facts import ProjectConfigurationFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-CONF0001")
def hardcoded_path_policy_count(
    subject: Table[ProjectConfigurationFact],
    *,
    minimum_paths: NonNegativeInt = 3,
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
) -> CountQuery:
    """Count hardcoded path-discovery policies in Python collections.

    Definition
    ----------
    Inspect simple assignments to names whose normalized words include `exclude`, `excluded`,
    `ignore`, `ignored`, `directory`, `directories`, `suffix`, or `suffixes`. Report only list,
    tuple, and set literals containing at least three strings, and read every entry for whether it
    is a filesystem path at all. Directory collections may contain safe path components. Suffix
    collections must contain dotted suffixes or suffix globs. Other policy names require at least
    one explicit separator, glob, hidden-name, or suffix marker.

    An entry written as a regular expression is not a path, whatever the name around it says. The
    same words this rule matches also name the pattern tables a project hands to a coverage
    reporter, a linter, or a rename step, and those entries carry backslash escapes, anchors,
    alternation, groups, and repetition that no path and no glob has. Reading the entries settles
    that where a table of known tool keys only postpones it, because every tool spells its own key
    differently while every regular expression is written the same way. An entry reading as a
    pattern therefore votes for nothing, and a collection holding only patterns is a pattern table
    rather than a path policy.

    Evidence
    --------
    Each finding locates the complete assignment, records the number of literal paths, and retains
    up to 32 exact entries. The result counts assignments rather than individual strings. The value
    is the number of qualifying assignments rather than the number of paths they hold.

    Exceptions
    ----------
    One or two local paths, computed collections, URLs, mixed nonstring literals, arbitrary names,
    generic exclusion lists without any path syntax, and pattern tables abstain. Fields on Pydantic
    model classes whose names end in `Configuration` are already typed policy and also abstain.
    Small algorithm-owned suffix tables can configure a higher threshold or disable the rule. No
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

    A coverage exclusion table such as `("pragma: no cover", "if TYPE_CHECKING:", "\\.\\.\\.")`
    reads as `0` as well, because those entries are source-line patterns rather than paths.

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
    Cites "The Python Standard Library", re
    https://docs.python.org/3.14/library/re.html
    """
    relations = subject
    vocabulary = "|".join(policy_names)
    word = rf"(?:^|[^a-z])(?:{vocabulary})(?:$|[^a-z])"
    suffix = r"(?:^|[^a-z])(?:suffix|suffixes)(?:$|[^a-z])"
    directory = r"(?:^|[^a-z])(?:directory|directories)(?:$|[^a-z])"
    pattern_syntax = r"[\^$|()+]|\\[^\w]|\\[dDwWsSbBAZ]"
    assignments = relations.records("assignments").filter(
        pl.col("name").str.to_lowercase().str.contains(word)
        & (pl.col("collection_kind") != "other")
        & (pl.col("values.length") >= minimum_paths)
        & ~pl.col("is_typed_configuration_field")
    )
    entries = relations.values("assignments.values").with_columns(
        pl.col("string_value").str.contains(pattern_syntax).alias("is_pattern")
    )
    value_shapes = entries.group_by("fact_id", "parent_id", maintain_order=True).agg(
        (
            (
                pl.col("string_value").str.starts_with(".")
                | pl.col("string_value").str.contains("*", literal=True)
            )
            & ~pl.col("is_pattern")
        )
        .all()
        .alias("all_suffixes"),
        (
            (
                pl.col("string_value").str.contains("/", literal=True)
                | pl.col("string_value").str.contains("\\", literal=True)
                | pl.col("string_value").str.contains("*", literal=True)
                | pl.col("string_value").str.starts_with(".")
            )
            & ~pl.col("is_pattern")
        )
        .any()
        .alias("any_path_syntax"),
        pl.col("is_pattern").all().alias("all_patterns"),
    )
    selected = assignments.join(
        value_shapes,
        left_on=["fact_id", "record_id"],
        right_on=["fact_id", "parent_id"],
        how="inner",
    ).filter(
        pl.when(pl.col("name").str.to_lowercase().str.contains(suffix))
        .then(pl.col("all_suffixes"))
        .when(pl.col("name").str.to_lowercase().str.contains(directory))
        .then(~pl.col("all_patterns"))
        .otherwise(pl.col("any_path_syntax"))
    )
    facts = relations.counted(selected)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "hardcoded path policy count",
            evidence=pl.col("evidence"),
        ),
    )
