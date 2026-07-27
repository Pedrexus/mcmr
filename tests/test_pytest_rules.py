from typing import TYPE_CHECKING

from mcmr.facts import (
    CallSite,
    ImportBindingFact,
    LiteralTestLoop,
    SourceSpan,
)
from mcmr.facts import (
    TestCaseGroup as CaseGroup,
)
from mcmr.facts import (
    TestCaseGroupFact as CaseGroupFact,
)
from mcmr.facts import (
    TestFunction as CaseFunction,
)
from mcmr.facts import (
    TestFunctionFact as FunctionTestsFact,
)
from mcmr.facts import (
    TestSuiteFact as SuiteFact,
)
from mcmr.rules.python.deterministic.testing.r0009 import conftest_import
from mcmr.rules.python.deterministic.testing.r0010 import legacy_tmpdir_fixture_count
from mcmr.rules.python.deterministic.testing.r0011 import parametrization_candidate_group_count
from mcmr.rules.python.deterministic.testing.r0012 import pytest_configuration_strictness
from mcmr.rules.python.deterministic.testing.r0013 import pytest_import_isolation
from mcmr.rules.python.deterministic.testing.r0014 import async_runner_auto_mode_conflict
from mcmr.rules.python.deterministic.testing.r0015 import coverage_without_branch_measurement
from mcmr.rules.python.deterministic.testing.r0016 import (
    direct_shared_test_state_mutation_count,
)
from mcmr.rules.python.deterministic.testing.r0017 import synchronous_test_asyncio_run_count
from mcmr.rules.python.deterministic.testing.r0018 import unowned_async_test_count
from mcmr.rules.python.deterministic.testing.r0019 import conditional_test_branch_count
from mcmr.rules.python.deterministic.testing.r0020 import owned_test_statement_count
from mcmr.rules.python.deterministic.testing.r0021 import manual_literal_test_case_loop_count
from mcmr.rules.python.deterministic.testing.r0022 import (
    finite_range_hypothesis_candidate_count,
)

if TYPE_CHECKING:
    from tests.conftest import Declared

SPAN = SourceSpan(path="tests/test_example.py")


def case(name: str, **declared: Declared) -> CaseFunction:
    """Return one test function of the example module, declaring the given observations."""
    return CaseFunction.model_validate({"name": name, "path": "tests/test_a.py"} | declared)


def function_tests(*declared: CaseFunction) -> FunctionTestsFact:
    """Return one fact holding the given test functions of the example module."""
    return FunctionTestsFact(key="tests", span=SPAN, tests=list(declared))


def case_groups(**declared: Declared) -> CaseGroupFact:
    """Return one fact holding the repeated cases under the single field naming them."""
    return CaseGroupFact.model_validate({"key": next(iter(declared)), "span": SPAN} | declared)


def test_conftest_import_cases() -> None:
    subject = ImportBindingFact(
        key="import",
        span=SPAN,
        name="client",
        imported_name="client",
        module="tests.conftest",
    )
    assert conftest_import(subject) == 1
    assert conftest_import(subject, allowed_modules=("tests.conftest",)) == 0
    assert conftest_import(subject.model_copy(update={"module": "tests.fixtures"})) == 0


def test_what_each_declared_test_function_requests_and_owns() -> None:
    """Every measure reads the collected test functions of one module and what each one owns."""
    fixtures = function_tests(
        case(
            "test_a",
            fixture_names=["tmpdir", "client"],
            requested_fixture_names=["tmpdir_factory"],
        ),
        case("helper", fixture_names=["tmpdir"], is_collected=False),
    )
    assert legacy_tmpdir_fixture_count(fixtures) == 2

    subject = function_tests(
        case(
            "test_sync",
            calls=[CallSite(qualified_name="asyncio.run", path="tests/test_a.py")],
            module_state_mutation_count=2,
            owned_conditional_count=3,
            owned_statement_count=30,
            parametrized_range_sizes=[10, 3],
        ),
        case("test_async_owned", is_async=True, marks=["pytest.mark.anyio"]),
        case("test_async_unowned", is_async=True),
        case("test_async_fixture", is_async=True, requested_fixture_names=["anyio_backend"]),
    )
    assert direct_shared_test_state_mutation_count(subject) == 2
    assert synchronous_test_asyncio_run_count(subject) == 1
    assert unowned_async_test_count(subject) == 1
    assert unowned_async_test_count(subject, anyio_auto=True) == 0
    assert conditional_test_branch_count(subject) == 3
    assert owned_test_statement_count(subject) == 30
    assert finite_range_hypothesis_candidate_count(subject) == 1
    assert finite_range_hypothesis_candidate_count(subject, minimum_cases=11) == 0


def test_pytest_configuration_cases() -> None:
    strict = SuiteFact(
        key="suite",
        span=SPAN,
        strict_controls={
            "strict_config": True,
            "strict_markers": True,
            "strict_parametrization_ids": True,
            "strict_xfail": True,
        },
        import_mode="importlib",
        anyio_mode="auto",
        asyncio_mode="auto",
        is_coverage_configured=True,
    )
    assert pytest_configuration_strictness(strict).value == "strict"
    assert pytest_import_isolation(strict) == "isolated"
    assert async_runner_auto_mode_conflict(strict)
    assert coverage_without_branch_measurement(strict)

    partial = strict.model_copy(
        update={
            "strict_controls": {"strict_config": True},
            "import_mode": "append",
            "asyncio_mode": "strict",
            "is_branch_coverage_enabled": True,
        }
    )
    assert pytest_configuration_strictness(partial).value == "partial"
    assert pytest_import_isolation(partial) == "appended"
    assert not async_runner_auto_mode_conflict(partial)
    assert not coverage_without_branch_measurement(partial)

    permissive = partial.model_copy(update={"strict_controls": {}, "import_mode": "unknown"})
    assert pytest_configuration_strictness(permissive).value == "permissive"
    assert pytest_import_isolation(permissive) == "invalid"


def test_repeated_literal_cases_one_parametrization_would_state_once() -> None:
    """Both measures look for a short example table written by hand rather than parametrized."""
    groups = case_groups(
        groups=[
            CaseGroup(
                normalized_syntax="assert normalize(SLOT) == SLOT",
                literal_vectors=[["A", "a"], ["B", "b"], ["C", "c"]],
            ),
            CaseGroup(
                normalized_syntax="assert duplicate(SLOT)",
                literal_vectors=[["A"], ["A"], ["B"]],
            ),
        ]
    )
    assert parametrization_candidate_group_count(groups) == 1
    assert parametrization_candidate_group_count(groups, minimum_cases=4) == 0

    loops = case_groups(
        loops=[
            LiteralTestLoop(case_count=3, owns_assertion=True),
            LiteralTestLoop(case_count=5, owns_assertion=False),
            LiteralTestLoop(case_count=2, owns_assertion=True),
        ]
    )
    assert manual_literal_test_case_loop_count(loops) == 1
    assert manual_literal_test_case_loop_count(loops, minimum_cases=4) == 0
