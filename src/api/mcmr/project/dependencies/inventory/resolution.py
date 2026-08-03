from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import model_validator

from ....domain.primitives import NonEmptyStr

if TYPE_CHECKING:
    from typing import Self


class DependencyResolution(FrozenModel):
    """Hold either one exact version or one explicit reason resolution failed."""

    version: NonEmptyStr | None = None
    failure: NonEmptyStr | None = None

    @model_validator(mode="after")
    def states_exactly_one_result(self) -> Self:
        """Require exactly one side of the resolution result."""
        if (self.version is None) == (self.failure is None):
            raise ValueError("dependency resolution needs exactly one version or failure")
        return self
