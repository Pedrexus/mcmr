from ..... import rule
from .....facts import ProjectConfigurationFact
from .....models import Count


@rule
def minimum_python_declaration(
    subject: ProjectConfigurationFact, *, minimum_version: str = "3.14"
) -> Count:
    """Keep project and tool Python targets explicit and mutually consistent.

    Definition
    ----------
    Parse `[project].requires-python` with `packaging`. Require it to exclude every Python 3
    minor below `minimum_version`. When Ruff, Pyrefly, ty, mypy, Pyright, or basedpyright is
    configured, require its target-version key and require that target to equal the minimum
    Python minor admitted by the project declaration. Ruff per-file targets must meet the same
    project minimum because a file cannot safely support less than the published package.

    Evidence
    --------
    Report a missing or invalid `pyproject.toml`, a missing or invalid project declaration, each
    configured tool without an explicit target, and each old or inconsistent target. Locations
    point to the relevant TOML declaration when it can be identified. The value is the number of
    missing or inconsistent Python target declarations.

    Exceptions
    ----------
    A type checker with no `[tool]` table is outside the project and is not required. Interpreter
    discovery is deliberately not accepted for a configured checker because it varies between
    developer machines and CI. Packaging upper bounds and exclusions remain valid when they
    preserve the declared minimum.

    Examples
    --------
    Good
    ~~~~
    `requires-python = ">=3.14"`, Ruff `target-version = "py314"`, and Pyrefly
    `python-version = "3.14"` agree.

    Bad
    ~~~
    `requires-python = ">=3.13"` permits an older interpreter. A configured `[tool.ty]` without
    `[tool.ty.environment].python-version` is missing a stable target. Ruff `py313` disagrees
    with a package whose minimum is Python 3.14.

    References
    ----------
    Cites "Python Packaging User Guide", `requires-python`
    https://packaging.python.org/en/latest/specifications/pyproject-toml/#requires-python
    Cites "packaging documentation", specifier API
    https://packaging.pypa.io/en/stable/specifiers.html
    Cites "Ruff documentation", configuration for `target-version`
    https://docs.astral.sh/ruff/settings/#target-version
    Cites "Pyrefly documentation", `python-version`
    https://pyrefly.org/en/docs/configuration/
    Cites "ty documentation", `python-version`
    https://docs.astral.sh/ty/reference/configuration/#python-version
    """
    try:
        required_minor = int(minimum_version.removeprefix("3."))
    except ValueError:
        raise ValueError(f"Unsupported minimum Python version {minimum_version!r}") from None
    if subject.python_target is None:
        return 1
    target = subject.python_target
    issues = int(
        target.project_minimum_minor is None or target.project_minimum_minor < required_minor
    )
    admitted = target.project_minimum_minor
    issues += sum(
        tool not in target.tool_target_minors
        or admitted is not None
        and target.tool_target_minors.get(tool) != admitted
        for tool in target.configured_tools
    )
    issues += sum(
        admitted is None or target_minor < admitted
        for target_minor in target.per_file_target_minors
    )
    return issues
