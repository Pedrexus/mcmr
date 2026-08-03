from typing import TYPE_CHECKING

from pydantic import model_validator

from ....policy import Boolean, Category, Numeric, RulePolicy
from ..metadata import FixDefinition, RuleDocumentation
from .groups import RuleDefinitionFields

if TYPE_CHECKING:
    from typing import Self

    from ....primitives.scope import RuleScope
    from ...runtime import RuleId, RuleLane


class RuleDefinition(RuleDefinitionFields.Judgment):
    """Describe one source-derived rule contract."""

    @property
    def callable(self) -> str:
        """Return the implementation import path."""
        return self.identity.callable

    @property
    def external(self) -> bool:
        """Return whether the rule needs external evidence."""
        return self.identity.external

    @property
    def fact(self) -> str:
        """Return the primary fact family name."""
        return self.identity.fact

    @property
    def family(self) -> str:
        """Return the structural rule family."""
        return self.identity.family

    @property
    def id(self) -> RuleId:
        """Return the stable rule identifier."""
        return self.identity.id

    @property
    def lane(self) -> RuleLane:
        """Return the execution lane."""
        return self.identity.lane

    @property
    def scope(self) -> RuleScope:
        """Return the language or general scope."""
        return self.identity.scope

    @model_validator(mode="after")
    def valid_policies(self) -> Self:
        """Require the owned policy to match this output contract."""
        self.validate_policy(self.policy)
        return self

    def validate_policy(
        self,
        candidate: RulePolicy | None,
        name: str = "policy",
    ) -> None:
        """Reject one policy that cannot fully judge this rule's output contract."""
        if candidate is None:
            return
        matches = (
            (self.output == "bool" and isinstance(candidate, Boolean))
            or (self.output in {"int", "float"} and isinstance(candidate, Numeric))
            or (self.output == "category" and isinstance(candidate, Category))
        )
        if not matches:
            raise TypeError(f"{self.id} {name} does not match its {self.output} output")
        if isinstance(candidate, Category):
            declared = candidate.good | candidate.neutral | candidate.bad
            if declared != set(self.categories):
                raise ValueError(
                    f"{self.id} {name} must classify every output category exactly once"
                )


RuleDefinition.model_rebuild(
    _types_namespace={
        "FixDefinition": FixDefinition,
        "RuleDocumentation": RuleDocumentation,
        "RulePolicy": RulePolicy,
    }
)
