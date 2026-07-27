from ..... import rule
from .....facts import QueryFact
from .....models import Count


@rule
def async_session_expiration_policy(subject: QueryFact) -> Count:
    """Require explicit non-expiring SQLAlchemy async session factories.

    Definition
    ----------
    Find calls statically resolved to SQLAlchemy `async_sessionmaker`. Report a factory unless it
    sets `expire_on_commit=False`. SQLAlchemy recommends this async setting so ordinary attribute
    access after commit does not attempt implicit database I/O. A factory expanded through
    unknown keyword arguments is left unreported because its effective policy cannot be proven.

    Evidence
    --------
    Each finding points to one factory call whose commit expiration remains enabled or unknown.
    The value is the number of actionable factories.

    Exceptions
    ----------
    Keep expiration only when the application deliberately refreshes or awaits every subsequent
    access and has tests proving that lifecycle. Direct `AsyncSession` construction and custom
    factory wrappers are not inferred by this narrow rule.

    Examples
    --------
    Bad
    ~~~
    `sessions = async_sessionmaker(engine)` retains the default commit expiration and is
    reported.

    Good
    ~~~~
    `sessions = async_sessionmaker(engine, expire_on_commit=False)` keeps post-commit attributes
    available without hidden I/O.

    References
    ----------
    Cites "SQLAlchemy documentation", asyncio documentation, preventing implicit I/O
    https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession
    Cites "SQLAlchemy documentation", async session factory API
    https://docs.sqlalchemy.org/en/21/orm/extensions/asyncio.html#sqlalchemy.ext.asyncio.async_sessionmaker
    """
    return sum(
        operation.kind == "async_sessionmaker"
        and operation.expire_on_commit
        and not operation.has_unknown_keywords
        for operation in subject.operations
    )
