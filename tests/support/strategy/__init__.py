from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hypothesis import strategies as st

    from mcmr.facts import Fact

from ..vocabulary import vocabulary
from .schema import SchemaStrategy


@cache
def facts_of[FactType: Fact](family: type[FactType]) -> st.SearchStrategy[FactType]:
    """Return the strategy building well-formed facts of one family, cached per family."""
    return SchemaStrategy(dialect=vocabulary(family)).of(family)


__all__ = ["facts_of"]
