from keyword import iskeyword
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt, model_validator

if TYPE_CHECKING:
    from typing import Self


class ImportRequest(FrozenModel):
    """Name one binding replacement source needs the renderer to make available."""

    module: str
    name: str = ""
    alias: str = ""
    level: NonNegativeInt = 0
    type_only: bool = False

    @property
    def binding(self) -> str:
        """Return the local name this import introduces."""
        return self.alias or self.name or self.module.split(".", 1)[0]

    @property
    def source(self) -> str:
        """Return the smallest ordinary import statement satisfying this request."""
        if self.name:
            imported = f"{self.name} as {self.alias}" if self.alias else self.name
            return f"from {'.' * self.level}{self.module} import {imported}"
        return f"import {self.module} as {self.alias}" if self.alias else f"import {self.module}"

    @model_validator(mode="after")
    def validate_python_names(self) -> Self:
        """Reject import syntax that Python could never parse."""
        if (not self.module and (not self.name or not self.level)) or (
            bool(self.module)
            and any(not part.isidentifier() or iskeyword(part) for part in self.module.split("."))
        ):
            raise ValueError("module must be a dotted Python identifier")
        if self.level and not self.name:
            raise ValueError("relative modules require a from import")
        if self.name and (not self.name.isidentifier() or iskeyword(self.name)):
            raise ValueError("imported name must be a Python identifier")
        if self.alias and (not self.alias.isidentifier() or iskeyword(self.alias)):
            raise ValueError("import alias must be a Python identifier")
        return self
