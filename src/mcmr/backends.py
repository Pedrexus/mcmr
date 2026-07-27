from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING

from .bases import FrozenFlexModel

if TYPE_CHECKING:
    from .facts import Fact


class ClassificationBackend(FrozenFlexModel, ABC):
    """Classify primitive evidence against one explicit closed rubric."""

    @abstractmethod
    async def classify[Category: StrEnum](
        self,
        subject: Fact,
        *,
        category: type[Category],
        instructions: str,
    ) -> Category:
        """Return exactly one allowed category supported by retained evidence."""


type RuleDependency = ClassificationBackend
