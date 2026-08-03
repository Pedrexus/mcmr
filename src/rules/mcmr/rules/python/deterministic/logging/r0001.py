import polars as pl

from ..... import rule
from .....domain.contracts import (
    FixSafety,
    Unit,
)
from .....facts import CallFact
from .....query import CountQuery, FindingQuery, FixQuery, RuleQuery
from .....table import CallRelation, Table


@rule("PY-LOGG0001", fix_safety=FixSafety.REVIEW)
def logger_boundary_bypass_count(
    subject: Table[CallFact],
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
) -> CountQuery:
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
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    owned_facts = (
        subject.lazy(CallRelation.MODULE_BINDINGS)
        .filter(pl.col("name") == preferred_logger)
        .select("fact_id")
        .unique()
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .filter(
            pl.col("qualified_name").is_in([preferred_logger, *direct_logger_symbols])
            & (pl.col("qualified_name") != preferred_logger)
        )
        .join(owned_facts, on="fact_id", how="anti")
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            "qualified_name",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    repairable = selected.filter(pl.col("callee_id").is_not_null())
    level = pl.col("qualified_name").str.split(".").list.last()
    chosen_level = (
        pl.when(level.is_in(["debug", "info", "warning", "error", "exception", "critical", "log"]))
        .then(level)
        .otherwise(pl.lit("info"))
    )
    logger_name = preferred_logger.rsplit(".", 1)[-1]
    rewrites = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.concat_str(pl.lit(f"{logger_name}."), chosen_level).alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("callee_id").alias("id"),
        pl.col("callee_path").alias("path"),
        pl.col("callee_start_line").alias("start_line"),
        pl.col("callee_start_column").alias("start_column"),
        pl.col("callee_end_line").alias("end_line"),
        pl.col("callee_end_column").alias("end_column"),
        pl.col("callee_kind").alias("kind"),
        pl.col("callee_text").alias("text"),
    )
    imports = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.lit(preferred_logger.rsplit(".", 1)[0]).alias("module"),
        pl.lit(logger_name).alias("name"),
        pl.lit("").alias("alias"),
        pl.lit(0, dtype=pl.UInt64).alias("level"),
        pl.lit(False).alias("type_only"),
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("`"),
                pl.col("qualified_name"),
                pl.lit(f"` bypasses the project logger `{preferred_logger}`"),
            ),
            (("logger boundary bypass count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Send each bypassing call through the logger this project already owns.",
            rewrites=rewrites,
            nodes=nodes,
            imports=imports,
        ),
    )
