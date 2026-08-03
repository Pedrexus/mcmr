from functools import cached_property

import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import FunctionFact
from ......query import FindingQuery, FixQuery, RuleQuery
from ......table import FunctionRelation, Table


class _ClassOwnedHelperFix:
    """Build one reviewable class-ownership rewrite from complete provider evidence."""

    def __init__(
        self,
        subject: Table[FunctionFact],
        frame: pl.LazyFrame,
        value: pl.Expr,
    ) -> None:
        self.subject = subject
        self.frame = frame
        self.value = value

    def query(self) -> FixQuery:
        """Move each helper and qualify its one proven call."""
        return FixQuery.build(
            "Move the sole-used helper into its owning class and qualify its call.",
            rewrites=self._rewrites(),
            nodes=pl.concat([self._move_nodes(), self._replacement_nodes()]),
        )

    @cached_property
    def _fixable(self) -> pl.LazyFrame:
        """Return findings whose declaration, owner method, and call are exact nodes."""
        return (
            self.frame.filter(
                self.value
                & pl.col("definition_id").is_not_null()
                & pl.col("sole_reference_owner_definition_id").is_not_null()
            )
            .join(
                self.subject.lazy(FunctionRelation.REFERENCES),
                left_on="entity_id",
                right_on="function_id",
                how="inner",
            )
            .with_columns(
                pl.concat_str(
                    pl.col("sole_reference_owner_class"),
                    pl.lit("."),
                    pl.col("text"),
                ).alias("qualified_call")
            )
        )

    def _move_nodes(self) -> pl.LazyFrame:
        """Address the helper declaration and its destination method."""
        return pl.concat(
            [
                self._fixable.select(
                    "fact_id",
                    pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
                    pl.lit(role).alias("role"),
                    pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                    pl.col(f"{prefix}_id").alias("id"),
                    pl.col(f"{prefix}_path").alias("path"),
                    pl.col(f"{prefix}_start_line").cast(pl.UInt64).alias("start_line"),
                    pl.col(f"{prefix}_start_column").cast(pl.UInt64).alias("start_column"),
                    pl.col(f"{prefix}_end_line").cast(pl.UInt64).alias("end_line"),
                    pl.col(f"{prefix}_end_column").cast(pl.UInt64).alias("end_column"),
                    pl.col(f"{prefix}_kind").alias("kind"),
                    pl.col(f"{prefix}_text").alias("text"),
                )
                for role, prefix in (
                    ("target", "definition"),
                    ("anchor", "sole_reference_owner_definition"),
                )
            ]
        )

    def _replacement_nodes(self) -> pl.LazyFrame:
        """Address the sole direct call replaced after moving its helper."""
        return self._fixable.select(
            "fact_id",
            pl.lit(1, dtype=pl.UInt64).alias("rewrite_order"),
            pl.lit("target").alias("role"),
            pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
            pl.col("node_id").alias("id"),
            pl.col("path_right").alias("path"),
            pl.col("start_line_right").cast(pl.UInt64).alias("start_line"),
            pl.col("start_column_right").cast(pl.UInt64).alias("start_column"),
            pl.col("end_line_right").cast(pl.UInt64).alias("end_line"),
            pl.col("end_column_right").cast(pl.UInt64).alias("end_column"),
            "kind",
            "text",
        )

    def _rewrites(self) -> pl.LazyFrame:
        """Return the ordered move and call replacement programs."""
        shared = [
            pl.lit("").alias("name"),
            pl.lit("").alias("symbol_id"),
            pl.lit("").alias("symbol_name"),
            pl.lit(False).alias("references_complete"),
        ]
        return pl.concat(
            [
                self._fixable.select(
                    "fact_id",
                    pl.lit(order, dtype=pl.UInt64).alias("rewrite_order"),
                    pl.lit(kind).alias("kind"),
                    source.alias("source"),
                    pl.lit(placement).alias("placement"),
                    *shared,
                )
                for order, kind, source, placement in (
                    (0, "move", pl.lit("@staticmethod\n"), "before"),
                    (1, "replace", pl.col("qualified_call"), ""),
                )
            ]
        )


@rule("ALL-FUNC0003", fix_safety=FixSafety.REVIEW)
def class_owned_module_helper(
    subject: Table[FunctionFact],
    *,
    minimum_lines: NonNegativeInt = 2,
    ignore_names: tuple[str, ...] = (),
) -> RuleQuery[bool]:
    """Detect a module helper used exclusively by one class method.

    Definition
    ----------
    Inspect undecorated module functions with one leading underscore and at least `minimum_lines`
    executable lines. Report only when the complete analyzed source set contains exactly one
    static load of the helper, that load is a direct call in a method body, and the method is
    defined directly on one class. This proves a narrow class-owned behavior candidate without
    rejecting private functional decomposition generally.

    Evidence
    --------
    Each finding cites the helper definition, owning class, method, and sole direct call. The
    review repair moves the helper before its sole calling method and qualifies that call
    through the owning class. The provider proves that no other static reference exists first.

    Exceptions
    ----------
    Module-private helpers called by module functions are permitted. Additional references,
    multiple callers, callback capture, attribute access, cross-file uses, decorators, module
    dunder hooks, nested functions, and uncertain ownership fail closed without a finding. The
    one-line helper rule separately owns helpers below the default two-line floor. `ignore_names`
    retains a helper whose module-level position is deliberate, and `minimum_lines` is the floor
    below which the one-line helper rule owns the candidate instead.

    Examples
    --------
    Bad
    ~~~
    `_parse_response` has two implementation lines and its only project reference is the direct
    call `ApiClient.request -> _parse_response(...)`. It is a candidate for `ApiClient` ownership.

    Good
    ~~~~
    `_parse_response` called by a module function remains valid. Helpers shared by several methods,
    passed as callbacks, or referenced outside the defining file are not assigned to one class.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", Public and Internal Interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    Cites "A Philosophy of Software Design", chapters 4 and 5
    Cites "Agile Software Development", single responsibility principle
    """
    decorator_counts = (
        subject.lazy(FunctionRelation.DECORATORS)
        .group_by("function_id")
        .agg(pl.len().cast(pl.UInt64).alias("decorator_count"))
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(
            decorator_counts,
            left_on="entity_id",
            right_on="function_id",
            how="left",
        )
        .with_columns(pl.col("decorator_count").fill_null(0))
    )
    value = (
        (pl.col("scope") == "module")
        & (pl.col("visibility") != "public")
        & (pl.col("decorator_count") == 0)
        & (pl.col("implementation_lines") >= minimum_lines)
        & (pl.col("reference_count") == 1)
        & (pl.col("sole_reference_owner_class") != "")
        & ~pl.col("name").is_in(list(ignore_names))
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "class owned module helper"),
        fix=_ClassOwnedHelperFix(subject, frame, value).query(),
    )
