from mcmr.facts import QueryFact, QueryOperation, SourceSpan
from mcmr.rules.python.deterministic.sqlalchemy.r0001 import async_session_expiration_policy
from mcmr.rules.python.deterministic.sqlalchemy.r0002 import session_commit_inside_loop
from mcmr.rules.python.deterministic.sqlalchemy.r0003 import sqlmodel_execute_scalars_api
from mcmr.rules.python.deterministic.sqlalchemy.r0004 import sqlmodel_redundant_scalars
from mcmr.rules.python.deterministic.sqlalchemy.r0005 import sqlmodel_primary_key_get


def test_sqlalchemy_operation_cases() -> None:
    subject = QueryFact(
        key="queries",
        span=SourceSpan(path="src/database.py"),
        operations=[
            QueryOperation(kind="async_sessionmaker", framework="sqlalchemy"),
            QueryOperation(
                kind="async_sessionmaker",
                framework="sqlalchemy",
                has_unknown_keywords=True,
            ),
            QueryOperation(
                kind="session_commit",
                framework="sqlalchemy",
                is_inside_loop=True,
            ),
            QueryOperation(kind="session_commit", framework="sqlalchemy"),
            QueryOperation(kind="execute_scalars", framework="sqlmodel"),
            QueryOperation(
                kind="exec_scalars",
                framework="sqlmodel",
                selected_expression_count=1,
            ),
            QueryOperation(
                kind="exec_scalars",
                framework="sqlmodel",
                selected_expression_count=2,
            ),
            QueryOperation(
                kind="primary_key_first",
                framework="sqlmodel",
                selected_expression_count=1,
                has_primary_key_equality=True,
            ),
            QueryOperation(
                kind="primary_key_first",
                framework="sqlmodel",
                selected_expression_count=1,
                has_primary_key_equality=True,
                has_execution_options=True,
            ),
        ],
    )
    assert async_session_expiration_policy(subject) == 1
    assert session_commit_inside_loop(subject) == 1
    assert sqlmodel_execute_scalars_api(subject) == 1
    assert sqlmodel_redundant_scalars(subject) == 1
    assert sqlmodel_primary_key_get(subject) == 1
