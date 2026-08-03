import polars as pl
from patos import FrozenModel

from .... import Boolean, Category, Numeric
from ....checking.evaluations import PreparedRule
from ....domain.policy import Policy
from ...contracts import FindingQuery, FixQuery, RuleQuery
from .compiled import CompiledRule


class RuleCompiler(FrozenModel):
    """Compile one lazy rule query into summary, evidence, and repair branches."""

    prepared: PreparedRule
    query: RuleQuery
    policy: Policy | None
    accepted_paths: list[str]
    rule_order: int

    @staticmethod
    def verdict(policy: Policy | None, output: str) -> tuple[pl.Expr, pl.Expr]:
        """Compile one policy directly against the query's scalar columns."""
        if isinstance(policy, Numeric):
            return RuleCompiler._numeric_verdict(policy, output)
        if isinstance(policy, Boolean):
            value = pl.col("boolean_value")
            return (value != policy.expected).fill_null(False), value.is_null()
        if isinstance(policy, Category):
            return RuleCompiler._category_verdict(policy)
        return pl.lit(False), pl.lit(True)

    def compile(self) -> CompiledRule:
        """Build every lazy branch without collecting any of them."""
        if (self.query.fix is None) != (self.prepared.rule.query_fix_safety is None):
            raise TypeError(
                f"{self.prepared.path} must declare repair safety exactly when it returns a fix"
            )
        findings = (self.query.findings or FindingQuery.empty()).normalized()
        judged = self._judged(self._values(findings))
        return CompiledRule(
            result=self._result(judged),
            failures=self._failures(judged),
            findings=self._findings(findings),
            fix_rewrites=self._fix_rewrites(),
            fix_nodes=self._fix_nodes(),
            fix_imports=self._fix_imports(),
        )

    @staticmethod
    def _category_verdict(policy: Category) -> tuple[pl.Expr, pl.Expr]:
        value = pl.col("category_value")
        failed = value.is_in(sorted(policy.bad)).fill_null(False)
        unassessed = (~value.is_in(sorted(policy.good | policy.bad))).fill_null(True)
        return failed, unassessed

    @staticmethod
    def _numeric_verdict(policy: Numeric, output: str) -> tuple[pl.Expr, pl.Expr]:
        value = pl.col("float_value" if output == "float" else "integer_value")
        failed = pl.lit(False)
        if policy.minimum is not None:
            failed |= value < policy.minimum
        if policy.maximum is not None:
            failed |= value > policy.maximum
        return failed.fill_null(False), value.is_null()

    def _accepted_language(self) -> pl.Expr:
        return (
            pl.lit(True)
            if str(self.prepared.scope) == "general"
            else pl.col("language") == pl.lit(str(self.prepared.scope))
        )

    def _failures(self, judged: pl.LazyFrame) -> pl.LazyFrame:
        return judged.filter(pl.col("failed")).select(
            pl.lit(self.rule_order, dtype=pl.UInt32).alias("rule_order"),
            pl.lit(self.prepared.path).alias("rule"),
            pl.exclude("failed", "unassessed"),
        )

    def _findings(self, findings: FindingQuery) -> pl.LazyFrame:
        return findings.rows.select(
            pl.lit(self.rule_order, dtype=pl.UInt32).alias("rule_order"),
            pl.lit(self.prepared.path).alias("rule"),
            pl.all(),
        )

    def _fix_imports(self) -> pl.LazyFrame:
        fix = self.query.fix
        return (FixQuery.empty_imports() if fix is None else fix.imports).select(
            pl.lit(self.rule_order, dtype=pl.UInt32).alias("rule_order"),
            pl.lit(self.prepared.path).alias("rule"),
            pl.all(),
        )

    def _fix_nodes(self) -> pl.LazyFrame:
        fix = self.query.fix
        return (FixQuery.empty_nodes() if fix is None else fix.nodes).select(
            pl.lit(self.rule_order, dtype=pl.UInt32).alias("rule_order"),
            pl.lit(self.prepared.path).alias("rule"),
            pl.all(),
        )

    def _fix_rewrites(self) -> pl.LazyFrame:
        fix = self.query.fix
        safety = self.prepared.rule.query_fix_safety
        return (FixQuery.empty_rewrites() if fix is None else fix.rewrites).select(
            pl.lit(self.rule_order, dtype=pl.UInt32).alias("rule_order"),
            pl.lit(self.prepared.path).alias("rule"),
            pl.lit("" if fix is None else fix.summary).alias("summary"),
            pl.lit("safe" if safety is None else str(safety)).alias("safety"),
            pl.all(),
        )

    def _judged(self, values: pl.LazyFrame) -> pl.LazyFrame:
        failed, unassessed = self.verdict(self.policy, self.prepared.contract[0])
        return values.with_columns(
            failed.alias("failed"),
            unassessed.alias("unassessed"),
        )

    def _result(self, judged: pl.LazyFrame) -> pl.LazyFrame:
        finding_count = pl.when(pl.col("failed")).then(pl.col("finding_count")).otherwise(0)
        return judged.select(
            pl.lit(self.rule_order, dtype=pl.UInt32).alias("rule_order"),
            pl.lit(self.prepared.path).alias("rule"),
            pl.len().cast(pl.UInt64).alias("observation_count"),
            pl.col("unassessed").sum().cast(pl.UInt64).alias("unassessed_count"),
            pl.col("failed").sum().cast(pl.UInt64).alias("failure_count"),
            finding_count.sum().cast(pl.UInt64).alias("finding_count"),
        )

    def _values(self, findings: FindingQuery) -> pl.LazyFrame:
        values = self.query.values.filter(
            self._accepted_language() & pl.col("path").is_in(self.accepted_paths)
        )
        if self.query.findings is None:
            return values
        counts = findings.rows.group_by("fact_id").agg(
            pl.len().cast(pl.UInt64).alias("finding_count")
        )
        return (
            values.drop("finding_count")
            .join(counts, on="fact_id", how="left")
            .with_columns(pl.col("finding_count").fill_null(0))
        )
