from typing import Literal

from ..... import rule
from .....facts import TestSuiteFact
from .....models import Choice, Finding, Measurement, Reported, counted


@rule
def pytest_configuration_strictness(
    subject: TestSuiteFact,
) -> Reported[Literal["strict", "partial", "permissive"]]:
    """Classify whether pytest rejects configuration and marker mistakes.

    Definition
    ----------
    Read the first pytest configuration selected by pytest's documented file precedence. Classify
    the project as `strict` when `strict = true`, `--strict`, or all four Pytest 9 controls are
    enabled. These are `strict_config`, `strict_markers`, `strict_parametrization_ids`, and
    `strict_xfail`. Classify any incomplete nonempty subset as `partial` and no enabled controls as
    `permissive`. Explicit individual values override global strict mode. The corresponding flags
    in `addopts` count when pytest provides one. This complements Ruff's PT rules because it checks
    project policy rather than Python test syntax.

    Evidence
    --------
    The finding names the configuration file the suite is read from, every strictness control
    that is off, and how many of them are on out of how many there are. The repair is a choice,
    since a suite is tightened one control at a time. The category is derived only from parsed
    configuration and never from a model opinion.

    Exceptions
    ----------
    A project that intentionally accepts dynamically registered third-party markers can configure
    `partial` as acceptable. Environment-only `PYTEST_ADDOPTS` is not assumed because it is not a
    reproducible repository setting.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: toml

       [tool.pytest.ini_options]
       addopts = "-q"

    Good
    ~~~~
    .. code-block:: toml

       [tool.pytest]
       strict = true

    References
    ----------
    Cites "pytest documentation", configuration reference
    https://docs.pytest.org/en/stable/reference/customize.html
    Cites "pytest documentation", strict configuration options
    https://docs.pytest.org/en/stable/reference/reference.html#configuration-options
    Cites "Ruff documentation", pytest-style rules
    https://docs.astral.sh/ruff/rules/#flake8-pytest-style-pt
    """
    controls = {
        "strict_config",
        "strict_markers",
        "strict_parametrization_ids",
        "strict_xfail",
    }
    enabled = {name for name, value in subject.strict_controls.items() if value}
    if subject.strict_mode or controls <= enabled:
        return Reported(value="strict")
    missing = sorted(controls - enabled)
    return Reported(
        value="partial" if controls.intersection(enabled) else "permissive",
        findings=(
            Finding(
                message=(
                    f"`{subject.span.path}` turns on "
                    f"{counted(len(controls) - len(missing), 'strictness control')} of the "
                    f"{len(controls)} there are, leaving "
                    f"{', '.join(f'`{name}`' for name in missing)} off"
                ),
                span=subject.span,
                measurements=(
                    Measurement(name="controls turned on", value=len(controls) - len(missing)),
                    Measurement(name="controls there are", value=len(controls)),
                ),
                repair=Choice(
                    question=f"turn on `{missing[0]}` in `{subject.span.path}`",
                    options=(
                        "enable them one at a time and repair what each one exposes",
                        "state the whole strict mode and take the failures at once",
                    ),
                ),
            ),
        ),
    )
