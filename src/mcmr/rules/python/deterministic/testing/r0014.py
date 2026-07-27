from ..... import rule
from .....facts import TestSuiteFact


@rule
def async_runner_auto_mode_conflict(subject: TestSuiteFact) -> bool:
    """Detect conflicting AnyIO and pytest-asyncio automatic modes.

    Definition
    ----------
    Read the effective pytest configuration and return true only when both AnyIO's `anyio_mode`
    and pytest-asyncio's `asyncio_mode` equal `auto`. AnyIO documents this exact combination as a
    plugin conflict. The check is deliberately narrower than generic async-test style rules and
    does not infer a conflict from installed dependencies alone.

    Evidence
    --------
    The finding identifies the effective pytest configuration file and both normalized option
    values. The suggested resolution keeps AnyIO automatic mode while restoring pytest-asyncio's
    documented strict default, though projects can make the inverse ownership choice.

    Exceptions
    ----------
    Explicit markers and backend fixtures without two automatic modes are accepted. Runtime flags
    supplied only outside repository configuration cannot be evaluated reproducibly.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: toml

       [tool.pytest.ini_options]
       anyio_mode = "auto"
       asyncio_mode = "auto"

    Good
    ~~~~
    .. code-block:: toml

       [tool.pytest.ini_options]
       anyio_mode = "auto"
       asyncio_mode = "strict"

    References
    ----------
    Cites "AnyIO documentation", testing guide
    https://anyio.readthedocs.io/en/stable/testing.html
    Cites "pytest-asyncio documentation", configuration
    https://pytest-asyncio.readthedocs.io/en/stable/reference/configuration.html
    Cites "pytest-asyncio documentation", concepts
    https://pytest-asyncio.readthedocs.io/en/stable/concepts.html
    """
    return subject.anyio_mode == "auto" and subject.asyncio_mode == "auto"
