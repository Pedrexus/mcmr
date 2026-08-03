from typing import TYPE_CHECKING

from mcmr.facts import ImportBindingFact, LiteralTestLoop, NodeRef, SourceSpan
from mcmr.facts import TestCallSite as CaseCallSite
from mcmr.facts import TestCaseGroup as CaseGroup
from mcmr.facts import TestCaseGroupFact as CaseGroupFact
from mcmr.facts import TestFunction as CaseFunction
from mcmr.facts import TestFunctionFact as FunctionTestsFact
from mcmr.facts import TestSuiteFact as SuiteFact
from mcmr.query import RuleQuery
from mcmr.rules.python import (
    async_runner_auto_mode_conflict,
    conditional_test_branch_count,
    conftest_import,
    coverage_without_branch_measurement,
    direct_shared_test_state_mutation_count,
    finite_range_hypothesis_candidate_count,
    legacy_tmpdir_fixture_count,
    manual_literal_test_case_loop_count,
    owned_test_statement_count,
    parametrization_candidate_group_count,
    pytest_configuration_strictness,
    pytest_import_isolation,
    synchronous_test_asyncio_run_count,
    unowned_async_test_count,
)
from mcmr.table import AnalysisSession

from ..support import query_value, retained_query

if TYPE_CHECKING:
    from pathlib import Path

    import polars as pl

    from ..support import Declared

_SPAN = SourceSpan(path="tests/test_example.py")


def case(name: str, **declared: Declared) -> CaseFunction:
    """Return one test function with the given collected observations."""
    return CaseFunction.model_validate({"name": name, "path": "tests/test_a.py"} | declared)


def function_tests(*declared: CaseFunction) -> FunctionTestsFact:
    """Return one fact holding the given test functions of the example module."""
    return FunctionTestsFact(key="tests", span=_SPAN, tests=list(declared))


def case_groups(**declared: Declared) -> CaseGroupFact:
    """Return one fact holding repeated cases under the single field naming them."""
    return CaseGroupFact.model_validate({"key": next(iter(declared)), "span": _SPAN} | declared)


def findings(query: RuleQuery) -> pl.DataFrame:
    """Collect one table rule's precise findings relation."""
    if query.findings is None:
        raise TypeError("the pytest rule emitted no findings relation")
    return query.findings.rows.collect()


def test_conftest_import_cases(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "test_example.py"
    source.parent.mkdir()
    source.write_text(
        "from tests.conftest import client\nfrom tests.fixtures import client as fixture_client\n"
    )
    table = AnalysisSession(
        tmp_path,
        suffixes=[".py"],
        typed_families=[ImportBindingFact.__name__],
    ).import_binding_tables()

    default = conftest_import.invoke_table(table, settings={}, dependencies={})
    allowed = conftest_import.invoke_table(
        table,
        settings={"allowed_modules": ["tests.conftest"]},
        dependencies={},
    )
    if not isinstance(default, RuleQuery) or not isinstance(allowed, RuleQuery):
        raise TypeError("the conftest rule returned a model query")

    assert default.values.collect().get_column("boolean_value").sum() == 1
    assert allowed.values.collect().get_column("boolean_value").sum() == 0


def test_what_each_declared_test_function_requests_and_owns() -> None:
    """Every measure reads all collected test functions of one module once."""
    fixtures = function_tests(
        case(
            "test_a",
            fixture_names=["tmpdir", "client"],
            requested_fixture_names=["tmpdir_factory"],
        ),
        case("helper", fixture_names=["tmpdir"], is_collected=False),
    )
    subject = function_tests(
        case(
            "test_sync",
            calls=[CaseCallSite(qualified_name="asyncio.run", path="tests/test_a.py")],
            module_state_mutation_count=2,
            owned_conditional_count=3,
            owned_statement_count=30,
            parametrized_range_sizes=[10, 3],
            node=NodeRef(
                id="test-sync",
                kind="test",
                span=SourceSpan(path="tests/test_a.py", start_line=12, end_line=24),
            ),
        ),
        case("test_async_owned", is_async=True, marks=["pytest.mark.anyio"]),
        case("test_async_unowned", is_async=True),
        case("test_async_fixture", is_async=True, requested_fixture_names=["anyio_backend"]),
    )
    statement_query = retained_query(subject, owned_test_statement_count)
    assert (
        query_value(retained_query(fixtures, legacy_tmpdir_fixture_count)),
        query_value(retained_query(subject, direct_shared_test_state_mutation_count)),
        query_value(retained_query(subject, synchronous_test_asyncio_run_count)),
        query_value(retained_query(subject, unowned_async_test_count)),
        query_value(retained_query(subject, unowned_async_test_count, discovery="automatic")),
        query_value(retained_query(subject, conditional_test_branch_count)),
        query_value(statement_query),
        query_value(retained_query(subject, finite_range_hypothesis_candidate_count)),
        query_value(
            retained_query(subject, finite_range_hypothesis_candidate_count, minimum_cases=11)
        ),
    ) == (2, 2, 1, 1, 0, 3, 30, 1, 0)
    assert findings(statement_query).item(0, "start_line") == 12


def strict_suite() -> SuiteFact:
    """Return a suite with every supported strictness control enabled."""
    return SuiteFact(
        key="suite",
        span=_SPAN,
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


def test_strict_pytest_configuration_cases() -> None:
    strict = strict_suite()
    assert (
        query_value(retained_query(strict, pytest_configuration_strictness)),
        query_value(retained_query(strict, pytest_import_isolation)),
        query_value(retained_query(strict, async_runner_auto_mode_conflict)),
        query_value(retained_query(strict, coverage_without_branch_measurement)),
    ) == ("strict", "isolated", True, True)


def test_partial_pytest_configuration_cases() -> None:
    partial = strict_suite().model_copy(
        update={
            "strict_controls": {"strict_config": True},
            "import_mode": "append",
            "asyncio_mode": "strict",
            "is_branch_coverage_enabled": True,
        }
    )
    appended = retained_query(partial, pytest_import_isolation)
    appended_findings = findings(appended)
    assert (
        query_value(retained_query(partial, pytest_configuration_strictness)),
        query_value(appended),
        appended_findings.item(0, "message"),
        appended_findings.item(0, "path"),
        appended_findings.item(0, "start_line"),
        query_value(retained_query(partial, async_runner_auto_mode_conflict)),
        query_value(retained_query(partial, coverage_without_branch_measurement)),
    ) == (
        "partial",
        "appended",
        "`tests/test_example.py` uses pytest import mode `append`, which changes `sys.path` "
        "during collection",
        "tests/test_example.py",
        1,
        False,
        False,
    )


def test_permissive_pytest_configuration_cases() -> None:
    permissive = strict_suite().model_copy(
        update={"strict_controls": {}, "import_mode": "unknown"}
    )
    assert query_value(retained_query(permissive, pytest_configuration_strictness)) == "permissive"
    invalid = retained_query(permissive, pytest_import_isolation)
    invalid_findings = findings(invalid)
    assert (
        query_value(invalid),
        invalid_findings.item(0, "message"),
    ) == (
        "invalid",
        "`tests/test_example.py` uses pytest import mode `unknown`, "
        "which pytest does not recognize",
    )


def test_repeated_literal_cases_one_parametrization_would_state_once() -> None:
    """Both measures read one table written by hand rather than parametrized."""
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
    assert query_value(retained_query(groups, parametrization_candidate_group_count)) == 1
    assert (
        query_value(retained_query(groups, parametrization_candidate_group_count, minimum_cases=4))
        == 0
    )

    loops = case_groups(
        loops=[
            LiteralTestLoop(case_count=3, owns_assertion=True),
            LiteralTestLoop(case_count=5, owns_assertion=False),
            LiteralTestLoop(case_count=2, owns_assertion=True),
        ]
    )
    assert query_value(retained_query(loops, manual_literal_test_case_loop_count)) == 1
    assert (
        query_value(retained_query(loops, manual_literal_test_case_loop_count, minimum_cases=4))
        == 0
    )
