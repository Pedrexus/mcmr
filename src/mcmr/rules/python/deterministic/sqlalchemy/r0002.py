from ..... import rule
from .....facts import QueryFact
from .....models import Count


@rule
def session_commit_inside_loop(subject: QueryFact) -> Count:
    """Find SQLAlchemy session commits nested inside loops.

    Definition
    ----------
    Resolve SQLAlchemy and SQLModel `Session` or `AsyncSession` parameters, annotated variables,
    direct constructors, and context managers created by known session factories. Report a
    `commit` call on one of those sessions when it is lexically nested in `for`, `async for`, or
    `while`. Committing each item adds transaction overhead and leaves partial durable progress
    when a later item fails.

    Evidence
    --------
    Each finding points to the inner commit. The count is the number of commits with a resolved
    session owner. The value is the number of commits with a resolved session owner inside a loop.

    Exceptions
    ----------
    Some ingestion workflows intentionally checkpoint durable progress per batch. Configure that
    boundary as an explicit batch loop rather than one transaction per row. Dynamic dependency
    injection and custom session wrappers are not guessed.

    Examples
    --------
    Bad
    ~~~
    `for row in rows` followed by `session.add(row)` and `session.commit()` is reported.

    Good
    ~~~~
    Add all rows inside `with session.begin()` and let the context commit once. For bounded
    checkpointing, commit once after each explicitly sized batch.

    References
    ----------
    Cites "SQLAlchemy documentation", session transaction
    https://docs.sqlalchemy.org/en/21/orm/session_transaction.html
    Cites "SQLAlchemy documentation", session lifecycle guidance
    https://docs.sqlalchemy.org/en/21/orm/session_basics.html#when-do-i-construct-a-session-when-do-i-commit-it-and-when-do-i-close-it
    """
    return sum(
        operation.kind == "session_commit" and operation.is_inside_loop
        for operation in subject.operations
    )
