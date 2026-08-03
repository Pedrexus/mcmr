from patos import FrozenModel
from pydantic import NonNegativeInt

from ....domain.policy import LengthDistribution, LengthDistributionValue
from ...foundation import NodeRef


class ProseSection(FrozenModel):
    """Retain normalized prose measurements after removing non-prose blocks."""

    text: str = ""
    character_count: NonNegativeInt = 0
    token_count: NonNegativeInt = 0
    sentence_word_counts: LengthDistributionValue = LengthDistribution(root=[])
    paragraph_word_counts: LengthDistributionValue = LengthDistribution(root=[])
    sentence_openers: list[str] = []
    node: NodeRef | None = None
