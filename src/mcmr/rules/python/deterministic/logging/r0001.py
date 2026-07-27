from ..... import rule
from .....facts import CallFact
from .....models import Count, FixSafety, Replace, SourceRewrite


@rule
def logger_boundary_bypass_count(
    subject: CallFact,
    *,
    preferred_logger: str = "common.log.logger",
    direct_logger_symbols: tuple[str, ...] = (
        "logging.Logger",
        "logging.LoggerAdapter",
        "logging.getLogger",
        "logging.debug",
        "logging.info",
        "logging.warning",
        "logging.error",
        "logging.exception",
        "logging.critical",
        "logging.fatal",
        "logging.log",
        "loguru.logger",
        "structlog.get_logger",
    ),
) -> Count:
    """Count direct logger provider calls outside the configured project boundary.

    Definition
    ----------
    Resolve absolute imports through module, class, function, and lambda scopes. Count calls to a
    configured logger constructor, module-level logging function, or direct logger object when the
    calling module does not define `preferred_logger`. The house default is
    `common.log.logger`. Calls through that project-owned logger remain valid. This rule does not
    inspect `print`, which remains Ruff `T201` ownership.

    Evidence
    --------
    Each finding records the exact resolved provider, preferred qualified logger, and source call.
    Assignments and parameters that shadow an imported name make resolution uncertain and suppress
    the finding. The result is the number of proven bypass calls. The value is the number of proven
    bypass calls.

    Exceptions
    ----------
    The module that defines the preferred logger may construct its underlying provider. Logging
    types used only in annotations, handler configuration, external adapters, unresolved calls, and
    relative imports receive no finding. Projects without the house logger can configure a
    different qualified symbol or disable this policy. `direct_logger_symbols` names the providers
    a call may reach, covering the standard library, loguru, and structlog by default, so a project
    using another logging library adds it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       import logging

       logger = logging.getLogger(__name__)
       logging.warning("retrying")

    Good
    ~~~~
    .. code-block:: python

       from common.log import logger

       logger.warning("retrying")

    References
    ----------
    Cites "Python HOWTOs", Configuring Logging for a Library
    https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library
    Cites "Python HOWTOs", Using logging in multiple modules
    https://docs.python.org/3/howto/logging-cookbook.html#using-logging-in-multiple-modules
    Cites "Loguru documentation", Migration from standard logging
    https://loguru.readthedocs.io/en/stable/resources/migration.html
    """
    owned = {preferred_logger, *direct_logger_symbols}
    if preferred_logger in subject.module_bindings:
        return 0
    return sum(
        call.qualified_name in owned and call.qualified_name != preferred_logger
        for call in subject.calls
    )


@logger_boundary_bypass_count.fix(is_default=True, safety=FixSafety.REVIEW)
def route_through_the_preferred_logger(
    subject: CallFact,
    *,
    preferred_logger: str = "common.log.logger",
    direct_logger_symbols: tuple[str, ...] = (
        "logging.Logger",
        "logging.LoggerAdapter",
        "logging.getLogger",
        "logging.debug",
        "logging.info",
        "logging.warning",
        "logging.error",
        "logging.exception",
        "logging.critical",
        "logging.fatal",
        "logging.log",
        "loguru.logger",
        "structlog.get_logger",
    ),
) -> list[SourceRewrite]:
    """Send each bypassing call through the logger this project already owns."""
    owned = {preferred_logger, *direct_logger_symbols}
    name = preferred_logger.rsplit(".", 1)[-1]
    return [
        Replace(target=call.callee, source=f"{name}.{level_of(call.qualified_name)}")
        for call in subject.calls
        if call.callee is not None
        and call.qualified_name in owned
        and call.qualified_name != preferred_logger
    ]


def level_of(qualified_name: str) -> str:
    """Return the level one bypassing call already asked for, or the one a bare call means."""
    level = qualified_name.rsplit(".", 1)[-1]
    known = {"debug", "info", "warning", "error", "exception", "critical", "log"}
    return level if level in known else "info"
