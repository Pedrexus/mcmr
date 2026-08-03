from patos import FrozenModel


class PlannerSample(FrozenModel):
    """Retain one bounded table planner measurement."""

    planning_nanoseconds: int
    execution_nanoseconds: int
    fix_planning_nanoseconds: int
    total_nanoseconds: int
