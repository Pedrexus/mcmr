from typing import Protocol


class RuleDependency(Protocol):
    """Mark one typed service a rule receives from the execution engine."""
