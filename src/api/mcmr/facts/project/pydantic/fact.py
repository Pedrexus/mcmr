from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .model import PydanticModelAnalysis


class PydanticModelFact(Fact):
    """Describe one Pydantic model and its validation contract."""

    models: list[PydanticModelAnalysis] = []
