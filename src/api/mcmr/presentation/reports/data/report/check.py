from typing import TYPE_CHECKING

from .....checking.session import allowed
from .failure import RuleFailure
from .groups import CheckReportFields

if TYPE_CHECKING:
    from pathlib import Path


class CheckReport(CheckReportFields.Outcome):
    """Retain what one catalog pass concluded before anybody renders it."""

    @property
    def failure_count(self) -> int:
        """Return every failure found, including ones outside a bounded view."""
        if self.total_failure_count is not None:
            return self.total_failure_count
        return len(self.failures)

    @property
    def finding_count(self) -> int:
        """Return how many findings the failures carry between them."""
        if self.total_finding_count is not None:
            return self.total_finding_count
        return sum(len(failure.findings) for failure in self.failures)

    @classmethod
    def of(cls, root: Path, judged: CheckReportFields.Judgment) -> CheckReport:
        """Return the report one judgment makes in the order it found failures."""
        return cls(
            root=str(root),
            file_count=judged.kernel.file_count,
            fact_count=judged.kernel.fact_count,
            rule_count=judged.engine.rule_count,
            rule_execution_count=judged.engine.rule_execution_count,
            skipped_rule_count=judged.engine.skipped_rule_count,
            rule_counts_by_lane=judged.engine.rule_counts_by_lane,
            rule_executions_by_lane=judged.engine.rule_executions_by_lane,
            skipped_rules=judged.engine.skipped_rules,
            table_query_count=judged.engine.table_query_count,
            table_queries_by_family=judged.engine.table_queries_by_family,
            observation_count=judged.engine.observation_count,
            unassessed_count=judged.unassessed_count,
            parse_failure_count=judged.kernel.parse_failure_count,
            kernel_milliseconds=judged.kernel.total_nanoseconds / 1_000_000,
            rule_milliseconds=judged.engine.execution_nanoseconds / 1_000_000,
            total_failure_count=judged.failure_count,
            total_finding_count=judged.finding_count,
            failures=[
                RuleFailure.of(
                    item,
                    allowed(
                        judged.policies.policy(
                            rule_id=item.definition.id,
                            candidate=item.definition.policy,
                        )
                    ),
                )
                for item in judged.failures
            ],
        )
