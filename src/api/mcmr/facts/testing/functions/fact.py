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

    class FunctionExecution(FunctionIdentity):
        """Retain marks, calls, owned structure, mutation, and parameterization."""

        marks: list[str] = []
        calls: list[TestCallSite] = []
        module_state_mutation_count: NonNegativeInt = 0
        owned_conditional_count: NonNegativeInt = 0
        owned_statement_count: NonNegativeInt = 0
        parametrized_range_sizes: list[NonNegativeInt] = []

    tests: list[TestFunction] = []
    quarantined_tests: list[QuarantinedTest] = []
