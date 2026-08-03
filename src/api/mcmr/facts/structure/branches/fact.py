from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .conditions.chain import ConditionalChain


class BranchFact(Fact):
    """Describe one conditional structure and the arms it selects between."""

    chains: list[ConditionalChain] = []
