from ..... import rule
from .....facts import QueryFact
from .....models import Count, Remove, Replace, SourceRewrite


@rule
def sqlmodel_execute_scalars_api(subject: QueryFact) -> Count:
    """Prefer SQLModel `exec` for exact scalar selections.

    Definition
    ----------
    Report `session.execute(select(Item)).scalars()` only when `Session` or `AsyncSession` and
    `select` resolve to SQLModel imports. The direct single-expression form has the same scalar
    result contract as SQLModel `exec` but bypasses SQLModel's typed convenience API.

    Evidence
    --------
    Each finding points to one complete `execute(...).scalars()` chain. The value is the number of
    exact chains.

    Exceptions
    ----------
    Raw SQLAlchemy sessions, multi-expression selects, textual SQL, execution options, statement
    variables, and row-shaped results remain unreported. SQLAlchemy owns those general cases.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       heroes = session.execute(select(Hero)).scalars().all()

    Good
    ~~~~
    .. code-block:: python

       heroes = session.exec(select(Hero)).all()

    References
    ----------
    Cites "SQLModel documentation", selection technical details
    https://sqlmodel.tiangolo.com/tutorial/select/#sqlmodels-sessionexec
    Cites "SQLAlchemy documentation", scalar-result guidance
    https://docs.sqlalchemy.org/en/21/orm/queryguide/select.html#selecting-orm-entities
    """
    return sum(
        operation.kind == "execute_scalars" and operation.framework == "sqlmodel"
        for operation in subject.operations
    )


@sqlmodel_execute_scalars_api.fix(is_default=True)
def use_sqlmodel_exec(subject: QueryFact) -> list[SourceRewrite]:
    """Call the SQLModel `exec` API, which already returns the scalar rows."""
    return [
        rewrite
        for operation in subject.operations
        if operation.kind == "execute_scalars"
        and operation.framework == "sqlmodel"
        and operation.execute_segment is not None
        and operation.scalars_segment is not None
        for rewrite in (
            Replace(target=operation.execute_segment, source="exec"),
            Remove(target=operation.scalars_segment),
        )
    ]
