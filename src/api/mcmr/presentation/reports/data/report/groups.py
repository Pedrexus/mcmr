from typing import TYPE_CHECKING, Protocol

from patos import FrozenModel
from pydantic import NonNegativeInt

from .....facts import SourceSpan

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .....domain.contracts import EngineStats, Observation, RuleDefinition
    from .....domain.policy import RulePolicies
    from .....kernel import KernelStats
    from .failure import RuleFailure


class CheckReportFields:
    """Group flat check report fields by their measurement source."""

    class Catalog(FrozenModel):
        """Retain repository, fact, rule, execution, and lane counts."""

        root: str
        file_count: NonNegativeInt = 0
        fact_count: NonNegativeInt = 0
        rule_count: NonNegativeInt = 0
        rule_execution_count: NonNegativeInt = 0
        skipped_rule_count: NonNegativeInt = 0
        rule_counts_by_lane: dict[str, NonNegativeInt] = {}

    class Coverage(Catalog):
        """Retain lane execution, skip, query, and observation counts."""

        rule_executions_by_lane: dict[str, NonNegativeInt] = {}
        skipped_rules: list[str] = []
        table_query_count: NonNegativeInt = 0
        table_queries_by_family: dict[str, NonNegativeInt] = {}
        observation_count: NonNegativeInt = 0
        unassessed_count: NonNegativeInt = 0
        parse_failure_count: NonNegativeInt = 0

    class Outcome(Coverage):
        """Retain timings, complete result counts, and bounded failures."""

        kernel_milliseconds: float = 0.0
        rule_milliseconds: float = 0.0
        total_failure_count: NonNegativeInt | None = None
        total_finding_count: NonNegativeInt | None = None
        failures: list[RuleFailure] = []

    class FailureIdentity(FrozenModel):
        """Retain a failed rule's identity, summary, location, and span."""

        rule: str
        callable: str = ""
        summary: str
        where: str
        span: SourceSpan

    class Assessment(Protocol):
        """State the judged observation fields a report projects."""

        @property
        def definition(self) -> RuleDefinition: ...

        @property
        def observation(self) -> Observation: ...

    class Judgment(Protocol):
        """State the completed judgment fields a report projects."""

        @property
        def engine(self) -> EngineStats: ...

        @property
        def failure_count(self) -> int: ...

        @property
        def failures(self) -> Sequence[CheckReportFields.Assessment]: ...

        @property
        def finding_count(self) -> int: ...

        @property
        def kernel(self) -> KernelStats: ...

        @property
        def policies(self) -> RulePolicies: ...

        @property
        def unassessed_count(self) -> int: ...
