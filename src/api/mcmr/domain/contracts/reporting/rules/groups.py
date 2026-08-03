from typing import TYPE_CHECKING

from patos import FrozenModel

from .identity import RuleIdentity

if TYPE_CHECKING:
    from ....policy import RulePolicy
    from ..metadata import FixDefinition, RuleDocumentation


class RuleDefinitionFields:
    """Group flat rule definition fields by contract and judgment."""

    class Contract(FrozenModel):
        """Retain identity, output, categories, settings, tables, and languages."""

        identity: RuleIdentity
        output: str
        unit: str = ""
        categories: list[str] = []
        settings: dict[str, str] = {}
        tables: list[str] = []
        languages: dict[str, list[str]] = {}

    class Judgment(Contract):
        """Retain documentation, fixes, and the owned policy."""

        documentation: RuleDocumentation
        fixes: list[FixDefinition] = []
        policy: RulePolicy | None = None
