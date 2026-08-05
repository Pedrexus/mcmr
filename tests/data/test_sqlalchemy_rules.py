from mcmr.domain.contracts import RuleContract, RuleValue
from mcmr.facts import NodeRef, QueryFact, QueryOperation, SourceSpan
from mcmr.plugins import fact_table
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.python import (
    async_session_expiration_policy,
    session_commit_inside_loop,
    sqlmodel_execute_scalars_api,
    sqlmodel_primary_key_get,
    sqlmodel_redundant_scalars,
)

_SPAN = SourceSpan(path="src/database.py")
_NODE = NodeRef(id="query", span=_SPAN)


def value(rule: RuleContract, subject: QueryFact) -> RuleValue:
    """Run one SQLAlchemy rule once over one in-memory query table."""
    table = fact_table(QueryFact, [subject])
    result = rule.invoke_table(table, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic query rule returned a model query")
    return scalar_frame_value(result.values.collect())


def test_sqlalchemy_operation_cases() -> None:
    subject = QueryFact(
        key="queries",
        span=_SPAN,
        operations=[
            QueryOperation(kind="async_sessionmaker", framework="sqlalchemy", node=_NODE),
            QueryOperation(
                kind="async_sessionmaker",
                framework="sqlalchemy",
                node=_NODE,
                has_unknown_keywords=True,
            ),
            QueryOperation(
                kind="session_commit",
                framework="sqlalchemy",
                node=_NODE,
                is_inside_loop=True,
            ),
            QueryOperation(kind="session_commit", framework="sqlalchemy", node=_NODE),
            QueryOperation(kind="execute_scalars", framework="sqlmodel", node=_NODE),
            QueryOperation(
                kind="execute_scalars",
                framework="sqlmodel",
                node=_NODE,
                has_execution_options=True,
            ),
            QueryOperation(
                kind="exec_scalars",
                framework="sqlmodel",
                node=_NODE,
                selected_expression_count=1,
            ),
            QueryOperation(
                kind="exec_scalars",
                framework="sqlmodel",
                node=_NODE,
                selected_expression_count=2,
            ),
            QueryOperation(
                kind="primary_key_first",
                framework="sqlmodel",
                node=_NODE,
                selected_expression_count=1,
                has_primary_key_equality=True,
            ),
            QueryOperation(
                kind="primary_key_first",
                framework="sqlmodel",
                node=_NODE,
                selected_expression_count=1,
                has_primary_key_equality=True,
                has_execution_options=True,
            ),
        ],
    )
    assert value(async_session_expiration_policy, subject) == 1
    assert value(session_commit_inside_loop, subject) == 1
    assert value(sqlmodel_execute_scalars_api, subject) == 1
    assert value(sqlmodel_redundant_scalars, subject) == 1
    assert value(sqlmodel_primary_key_get, subject) == 1
