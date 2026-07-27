from enum import StrEnum, auto
from typing import TYPE_CHECKING

from pydantic import NonNegativeInt

from .bases import FrozenFlexModel
from .models import RuleValue
from .policy import Numeric, Policy
from .projections import JsonRendering, Rendering
from .runs import FailingSite, RuleRecord, RunIdentity, RunRecord, RunStats, allowed, section

if TYPE_CHECKING:
    from collections.abc import Sequence


class Incomparable(Exception):
    """Refuse two runs that were not judged the same way, rather than subtract them anyway."""


class Movement(FrozenFlexModel):
    """One site that failed in both runs, and the two values it failed with."""

    fact: str
    before: RuleValue
    after: RuleValue


class RuleChange(FrozenFlexModel):
    """How one rule moved between two runs that judged it the same way.

    A site that arrived and a site that grew are both the repository getting worse, and a site that
    went and a site that shrank are both it getting better, so `drift` counts all four together and
    is the one number the report orders by.
    """

    rule: str
    allowed: str = ""
    appeared: tuple[FailingSite, ...] = ()
    resolved: tuple[FailingSite, ...] = ()
    worsened: tuple[Movement, ...] = ()
    eased: tuple[Movement, ...] = ()

    @property
    def drift(self) -> int:
        """Return how far this rule moved against the project, positive when it got worse."""
        return len(self.appeared) + len(self.worsened) - len(self.resolved) - len(self.eased)

    @property
    def moved(self) -> bool:
        """Return whether anything about this rule changed at all between the two runs."""
        return bool(self.appeared or self.resolved or self.worsened or self.eased)

    def summary(self) -> str:
        """Return the one line a report shows for this rule."""
        return (
            f"{self.rule} {self.drift:+d} allowed {self.allowed or 'nothing stated'}, "
            f"{len(self.appeared)} appeared, {len(self.resolved)} resolved, "
            f"{len(self.worsened)} worse, {len(self.eased)} easier"
        )


class RunComparison(FrozenFlexModel):
    """What changed between one recorded run and a later one.

    Only the rules both runs judged the same way reach the counts a reader reads as a direction. A
    rule the baseline never held cannot have regressed against it, and a rule whose contract or
    whose bar moved is measuring something else now, so each of those travels in a list of its own
    and is named rather than folded into a number that would be wrong.
    """

    profile: str
    baseline: RunIdentity
    current: RunIdentity
    before: NonNegativeInt = 0
    after: NonNegativeInt = 0
    regressed: tuple[RuleChange, ...] = ()
    improved: tuple[RuleChange, ...] = ()
    shifted: tuple[RuleChange, ...] = ()
    introduced: tuple[RuleRecord, ...] = ()
    retired: tuple[RuleRecord, ...] = ()
    redefined: tuple[str, ...] = ()

    @property
    def catalog_moved(self) -> bool:
        """Return whether the catalog itself differs between the two runs."""
        return bool(self.introduced or self.retired or self.redefined)

    @classmethod
    def between(cls, baseline: RunRecord, current: RunRecord) -> RunComparison:
        """Compare two runs, refusing the pair whose profiles never agreed on what to accept."""
        if baseline.profile != current.profile:
            raise Incomparable(
                f"the baseline was judged under the {baseline.profile} profile and this run "
                f"under {current.profile}, so the two verdicts state different intentions"
            )
        before, after = baseline.index(), current.index()
        shared = before.keys() & after.keys()
        comparable = sorted(
            rule for rule in shared if before[rule].judgment == after[rule].judgment
        )
        changes = [change(before[rule], after[rule]) for rule in comparable]
        moved = [item for item in changes if item.moved]
        return cls(
            profile=current.profile,
            baseline=baseline.identity,
            current=current.identity,
            before=sum(len(before[rule].failing) for rule in comparable),
            after=sum(len(after[rule].failing) for rule in comparable),
            regressed=ordered([item for item in moved if item.drift > 0], worst_first=True),
            improved=ordered([item for item in moved if item.drift < 0], worst_first=False),
            shifted=ordered([item for item in moved if not item.drift], worst_first=False),
            introduced=tuple(after[rule] for rule in sorted(after.keys() - before.keys())),
            retired=tuple(before[rule] for rule in sorted(before.keys() - after.keys())),
            redefined=tuple(
                sorted(rule for rule in shared if before[rule].judgment != after[rule].judgment)
            ),
        )


class SeriesPoint(FrozenFlexModel):
    """One recorded run in the order it happened, beside how it moved from the run before it.

    `drift` is counted over the rules this run and the one before it judged the same way, so a
    catalog that grew between them moves the totals without moving the direction. When the catalog
    did move, `catalog_moved` says so, because a reader comparing the totals column deserves to
    know that those two numbers were not counting the same rules.
    """

    identity: RunIdentity
    catalog: str
    stats: RunStats
    rule_count: NonNegativeInt = 0
    failing: NonNegativeInt = 0
    failing_rules: NonNegativeInt = 0
    unassessed: NonNegativeInt = 0
    drift: int | None = None
    catalog_moved: bool = False


class RunSeries(FrozenFlexModel):
    """Every run one repository recorded under one profile, oldest first.

    A series that mixed profiles would be a line drawn through two different questions, so the
    profile selects the runs rather than annotating them.
    """

    profile: str
    points: tuple[SeriesPoint, ...] = ()
    recorded: NonNegativeInt = 0

    @classmethod
    def of(cls, records: Sequence[RunRecord], profile: str, limit: int = 0) -> RunSeries:
        """Return the runs recorded under one profile, each held against the one before it.

        The direction is computed over the whole series and the window is taken afterwards, so the
        first row of a bounded view still says how it moved from the run it actually followed.
        """
        under = [record for record in records if record.profile == profile]
        points = [
            point(record, under[index - 1] if index else None)
            for index, record in enumerate(under)
        ]
        return cls(
            profile=profile,
            points=tuple(points[-limit:] if limit else points),
            recorded=len(under),
        )


class ReportFormat(StrEnum):
    """Say whether a run report is rendered for a person reading it or for another tool."""

    TEXT = auto()
    JSON = auto()

    def comparison(self, limit: int) -> Rendering[RunComparison]:
        """Return the rendering a comparison of two runs takes in this format."""
        return ComparisonText(limit=limit) if self is ReportFormat.TEXT else JsonRendering()

    def series(self) -> Rendering[RunSeries]:
        """Return the rendering a series of runs takes in this format."""
        return SeriesText() if self is ReportFormat.TEXT else JsonRendering()


class ComparisonText(FrozenFlexModel):
    """Render a comparison as what got worse, what got better, and what is newly judged."""

    limit: NonNegativeInt = 10

    def render(self, projection: RunComparison) -> str:
        """State the direction, then name the rules that moved and the ones that cannot be."""
        drift = projection.after - projection.before
        lines = [
            f"MCMR run comparison under the {projection.profile} profile",
            f"from {projection.baseline.label} at {projection.baseline.taken_at} "
            f"to {projection.current.label} at {projection.current.taken_at}",
            "",
            f"{projection.before} failing sites became {projection.after} ({drift:+d}) across the "
            f"rules both runs judged the same way",
            f"{len(projection.introduced)} rules newly judged, {len(projection.retired)} retired, "
            f"{len(projection.redefined)} redefined",
        ]
        lines += section(
            "Regressed", (item.summary() for item in projection.regressed), self.limit
        )
        lines += section("Improved", (item.summary() for item in projection.improved), self.limit)
        lines += section("Shifted", (item.summary() for item in projection.shifted), self.limit)
        lines += section(
            "Newly judged", (self.arrival(item) for item in projection.introduced), self.limit
        )
        lines += section(
            "Retired", (self.arrival(item) for item in projection.retired), self.limit
        )
        lines += section("Redefined", projection.redefined, self.limit)
        return "\n".join(lines)

    def arrival(self, record: RuleRecord) -> str:
        """Return one line for a rule only one of the two runs held."""
        return f"{record.rule} {len(record.failing)} failing, allowed {allowed(record.policy)}"


class SeriesText(FrozenFlexModel):
    """Render a series as one row per recorded run, oldest first, with the direction beside it."""

    def render(self, projection: RunSeries) -> str:
        """Draw the header and one row per run, marking where the catalog itself moved."""
        return "\n".join(
            [
                f"MCMR trend over {len(projection.points)} of {projection.recorded} runs "
                f"recorded under the {projection.profile} profile",
                "",
                f"{'when':<24} {'commit':<10} {'files':>6} {'rules':>6} "
                f"{'failing':>8} {'drift':>7}  catalog",
                *(self.row(point) for point in projection.points),
            ]
        )

    def row(self, point: SeriesPoint) -> str:
        """Return one run as a row, saying nothing about a direction it cannot state."""
        drift = "first" if point.drift is None else f"{point.drift:+d}"
        mark = "moved" if point.catalog_moved else "same"
        return (
            f"{point.identity.taken_at:<24} {point.identity.label:<10} "
            f"{point.stats.file_count:>6} {point.rule_count:>6} "
            f"{point.failing:>8} {drift:>7}  {point.catalog} {mark}"
        )


def change(before: RuleRecord, after: RuleRecord) -> RuleChange:
    """Return how one rule moved between two runs that held it to the same bar.

    A site failing in both runs is compared by how far outside the bar it sits, so a count that
    grew reads as worse and one that shrank reads as better even though the site never cleared.
    A rule whose values carry no magnitude reports only that a site failed or stopped failing,
    because one rejected category is not further from acceptable than another.
    """
    was, now = before.sites, after.sites
    movements = [
        Movement(fact=fact, before=was[fact].value, after=now[fact].value)
        for fact in sorted(was.keys() & now.keys())
        if was[fact].value != now[fact].value
    ]
    return RuleChange(
        rule=after.rule,
        allowed=allowed(after.policy),
        appeared=tuple(now[site] for site in sorted(now.keys() - was.keys())),
        resolved=tuple(was[site] for site in sorted(was.keys() - now.keys())),
        worsened=tuple(
            item
            for item in movements
            if excess(after.policy, item.after) > excess(after.policy, item.before)
        ),
        eased=tuple(
            item
            for item in movements
            if excess(after.policy, item.after) < excess(after.policy, item.before)
        ),
    )


def excess(policy: Policy | None, value: RuleValue) -> float:
    """Return how far one value sits outside what a profile accepted, as a magnitude."""
    if not isinstance(policy, Numeric) or isinstance(value, str | bool):
        return 0.0
    below = policy.minimum - value if policy.minimum is not None else 0.0
    above = value - policy.maximum if policy.maximum is not None else 0.0
    return max(below, above, 0.0)


def ordered(changes: list[RuleChange], *, worst_first: bool) -> tuple[RuleChange, ...]:
    """Return the changes in the order a report lists them, ties broken by identifier."""
    sign = -1 if worst_first else 1
    return tuple(sorted(changes, key=lambda item: (sign * item.drift, item.rule)))


def point(record: RunRecord, previous: RunRecord | None) -> SeriesPoint:
    """Return one run as a series point, held against the run that came before it."""
    against = RunComparison.between(previous, record) if previous is not None else None
    return SeriesPoint(
        identity=record.identity,
        catalog=record.catalog,
        stats=record.stats,
        rule_count=len(record.rules),
        failing=record.failing_count,
        failing_rules=record.failing_rule_count,
        unassessed=record.unassessed_count,
        drift=None if against is None else against.after - against.before,
        catalog_moved=against is not None and against.catalog_moved,
    )
