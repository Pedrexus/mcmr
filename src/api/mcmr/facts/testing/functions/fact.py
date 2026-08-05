from typing import TYPE_CHECKING

from patos import FrozenModel

from ...foundation import Fact, NodeRef

if TYPE_CHECKING:
    from pydantic import NonNegativeInt

    from ..suite.quarantined import QuarantinedTest
    from .call import TestCallSite
    from .function import TestFunction


class TestFunctionFact(Fact):
    """Describe one test function and its fixtures and assertions."""

    class FunctionIdentity(FrozenModel):
        """Retain test identity, source, collection, async, and fixture evidence."""

        name: str
        path: str
        node: NodeRef | None = None
        is_collected: bool = True
        is_async: bool = False
        fixture_names: list[str] = []
        requested_fixture_names: list[str] = []

    class FunctionBehavior(FunctionIdentity):
        """Retain marks, calls, body shape, literals, assertions, and targets."""

        marks: list[str] = []
        calls: list[TestCallSite] = []
        body_shape: str = ""
        literal_values: list[str] = []
        assertion_shapes: list[str] = []
        direct_targets: list[str] = []
        reachable_targets: list[str] = []

    class FunctionExecution(FunctionBehavior):
        """Retain owned structure, mutation, and parameterization metrics."""

        module_state_mutation_count: NonNegativeInt = 0
        owned_conditional_count: NonNegativeInt = 0
        owned_statement_count: NonNegativeInt = 0
        parametrized_range_sizes: list[NonNegativeInt] = []
        generated_parametrization_count: NonNegativeInt = 0

    tests: list[TestFunction] = []
    quarantined_tests: list[QuarantinedTest] = []
