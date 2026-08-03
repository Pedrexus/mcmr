from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .declaration import SymbolReach


class SymbolReachFact(Fact):
    """Describe how far references to one module's declarations spread."""

    is_test_module: bool = False
    declarations: list[SymbolReach] = []
