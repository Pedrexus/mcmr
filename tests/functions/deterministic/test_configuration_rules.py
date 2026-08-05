from typing import TYPE_CHECKING

from mcmr.facts import ConfigurationAssignment, ProjectConfigurationFact
from mcmr.rules.general import hardcoded_path_policy_count

from .support import answer, fact

if TYPE_CHECKING:
    from typing import Literal


def assignment(
    name: str,
    kind: Literal["list", "tuple", "set", "other"],
    *values: str,
    typed: bool = False,
) -> ConfigurationAssignment:
    """Return one configuration assignment with the selected values."""
    return ConfigurationAssignment(
        name=name,
        collection_kind=kind,
        values=list(values),
        is_typed_configuration_field=typed,
    )


def configuration(*assignments: ConfigurationAssignment) -> ProjectConfigurationFact:
    """Return one project configuration fact holding these assignments."""
    return fact(ProjectConfigurationFact, assignments=list(assignments))


def counted(subject: ProjectConfigurationFact, **settings: int) -> int:
    """Return how many hardcoded path policies one configuration holds."""
    return int(answer(hardcoded_path_policy_count, subject, **settings).value)


def test_a_path_policy_is_a_collection_of_paths_written_under_a_policy_name() -> None:
    """A name from the vocabulary is not enough, and a suffix list has to hold only suffixes.

    The last pair is the branch a coverage exclusion for `...` had been swallowing along with the
    rest of this body.
    """
    subject = configuration(
        assignment("excluded_directories", "list", ".git", ".venv", "build"),
        assignment("ignored", "list", "alpha", "beta", "gamma"),
        assignment("ignored_suffixes", "tuple", ".pyc", ".so", "*.egg-info", typed=True),
    )
    suffixes = configuration(assignment("ignored_suffixes", "tuple", ".pyc", ".so", "*.egg-info"))
    mixed = configuration(assignment("ignored_suffixes", "tuple", ".pyc", "build", ".so"))

    assert (counted(subject), counted(subject, minimum_paths=4)) == (1, 0)
    assert (counted(suffixes), counted(mixed)) == (1, 0)


def test_an_entry_written_as_a_regular_expression_is_not_a_path() -> None:
    """A project spells its coverage exclusions and its lint patterns with the same words.

    Every entry in those tables is a source-line regex, and the backslash escapes in one such as
    `\\.\\.\\.` used to read as Windows separators, which is what made the collection look like a
    list of paths. A real Windows path still reads as one, because a separator is a backslash
    before a name rather than before a metacharacter.
    """
    coverage = configuration(
        assignment(
            "exclude_lines",
            "list",
            "pragma: no cover",
            "if TYPE_CHECKING:",
            "if __name__ == .__main__.:",
            r"\.\.\.",
        )
    )
    patterns = configuration(
        assignment("ignore_patterns", "tuple", "^test_", r"\d+", r".*_pb2\.py")
    )
    directories = configuration(
        assignment("excluded_directories", "list", r"^\.git$", r"^build$", r"^dist$")
    )
    suffixes = configuration(
        assignment("ignored_suffixes", "tuple", r".*\.pyc", r".*\.so", r".*\.egg")
    )
    windows = configuration(
        assignment("ignored", "list", "build\\temp", "dist\\wheel", "out\\cache")
    )

    assert (counted(coverage), counted(patterns)) == (0, 0)
    assert (counted(directories), counted(suffixes)) == (0, 0)
    assert counted(windows) == 1
