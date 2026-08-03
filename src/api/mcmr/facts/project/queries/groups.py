from typing import Literal

from patos import FrozenModel
from pydantic import NonNegativeInt


class QueryOperationFields(FrozenModel):
    """Retain query kind, framework, transaction, shape, and selection count."""

    kind: Literal[
        "async_sessionmaker",
        "session_commit",
        "execute_scalars",
        "exec_scalars",
        "primary_key_first",
    ]
    framework: Literal["sqlalchemy", "sqlmodel"]
    is_inside_loop: bool = False
    expire_on_commit: bool = True
    has_unknown_keywords: bool = False
    selected_expression_count: NonNegativeInt = 0
    has_primary_key_equality: bool = False
