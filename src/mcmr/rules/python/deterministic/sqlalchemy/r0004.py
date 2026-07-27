from ..... import rule
from .....facts import QueryFact
from .....models import Count, Remove, SourceRewrite


@rule
def sqlmodel_redundant_scalars(subject: QueryFact) -> Count:
    """Remove scalar extraction repeated after SQLModel `exec`.

    Definition
    ----------
    Report `session.exec(select(Item)).scalars()` only when the session and `select` resolve to
    SQLModel and the select contains exactly one expression. SQLModel already applies scalar
    extraction for that statement shape.

    Evidence
    --------
    Each finding points to one redundant `scalars` call. The value is the number of exact chains.

    Exceptions
    ----------
    Multi-expression selects and unresolved sessions remain unreported because SQLModel preserves
    row-shaped results for those statements.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       heroes = session.exec(select(Hero)).scalars().all()

    Good
    ~~~~
    .. code-block:: python

       heroes = session.exec(select(Hero)).all()

    References
    ----------
    Cites "SQLModel documentation", selection technical details
    https://sqlmodel.tiangolo.com/tutorial/select/#sqlmodels-sessionexec
    Cites "SQLModel documentation", compact selection example
    https://sqlmodel.tiangolo.com/tutorial/select/#compact-version
    """
    return sum(
        operation.kind == "exec_scalars"
        and operation.framework == "sqlmodel"
        and operation.selected_expression_count == 1
        for operation in subject.operations
    )


@sqlmodel_redundant_scalars.fix(is_default=True)
def remove_redundant_scalars(subject: QueryFact) -> list[SourceRewrite]:
    """Drop the `scalars` segment that SQLModel `exec` already applied."""
    return [
        Remove(target=operation.scalars_segment)
        for operation in subject.operations
        if operation.scalars_segment is not None
        and operation.kind == "exec_scalars"
        and operation.framework == "sqlmodel"
        and operation.selected_expression_count == 1
    ]
