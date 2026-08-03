from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .failure import FailureScenario


class TestStrategyFields(Fact):
    """Retain requirements, risks, boundaries, scenarios, types, controls, and services."""

    requirements: list[str] = []
    risks: list[str] = []
    boundaries: list[str] = []
    failure_scenarios: list[FailureScenario] = []
    test_types: list[str] = []
    state_controls: list[str] = []
    external_services: list[str] = []
