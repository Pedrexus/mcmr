import re
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import model_validator

from ...domain.contracts import (
    FixSafety,
    RuleId,
    RuleLane,
    RuleScope,
)
from ...domain.policy import Boolean, Category, Numeric, RulePolicy

if TYPE_CHECKING:
    from typing import Self


class _CatalogContracts:
    """Own rulebook identities, source contracts, and judged definitions."""

    class Documentation(FrozenModel):
        """Retain the complete reStructuredText documentation of one rule."""

        summary: str
        definition: str
        evidence: str = ""
        exceptions: str = ""
        examples: str
        references: list[str] = []

    class Fix(FrozenModel):
        """Describe one validated fix attached to a catalog rule."""

        name: str
        callable: str
        is_default: bool
        safety: FixSafety

    class Identity(FrozenModel):
        """Identify one rule and the fact family where it belongs."""

        id: RuleId
        callable: str
        scope: RuleScope
        lane: RuleLane
        external: bool = False
        family: str
        fact: str

    class Fields:
        """Group flat rule definition fields by contract and judgment."""

        class Contract(FrozenModel):
            """Retain identity, output, categories, settings, tables, and languages."""

            identity: _CatalogContracts.Identity
            output: str
            unit: str = ""
            categories: list[str] = []
            settings: dict[str, str] = {}
            tables: list[str] = []
            languages: dict[str, list[str]] = {}

        class Judgment(Contract):
            """Retain documentation, fixes, and the owned policy."""

            documentation: _CatalogContracts.Documentation
            fixes: list[_CatalogContracts.Fix] = []
            policy: RulePolicy | None = None

    class Definition(Fields.Judgment):
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


FixDefinition = _CatalogContracts.Fix
RuleDefinition = _CatalogContracts.Definition
RuleDocumentation = _CatalogContracts.Documentation
RuleIdentity = _CatalogContracts.Identity


def parse_identity(module: str, identifier: RuleId) -> tuple[RuleScope, RuleLane, str, str]:
    """Validate one rule identity against its structural plugin path."""
    path = _identity_path(module)
    scope = RuleScope(path.group(1))
    lane = RuleLane(path.group(2))
    family = path.group(3)
    slot = _identity_slot(module, identifier, scope, family)
    if not slot.startswith(lane.slot):
        raise ValueError(
            f"Rule ID {identifier} is in the {lane} lane, whose numbers begin with "
            f"{lane.slot}, so {slot} belongs to another lane"
        )
    return scope, lane, family, slot


def _identity_path(module: str) -> re.Match[str]:
    """Match the scope, lane, and family encoded by one module path."""
    scopes = "|".join(RuleScope)
    lanes = "|".join(RuleLane)
    pattern = (
        rf"(?:[A-Za-z_]\w*\.)*rules\.({scopes})\.({lanes})\.([a-z][a-z0-9_]*)"
        rf"(?:\.[a-z][a-z0-9_]*)+"
    )
    if (match := re.fullmatch(pattern, module)) is None:
        raise ValueError(f"Rule module {module} does not follow the rule plugin path")
    return match


def _identity_slot(module: str, identifier: RuleId, scope: RuleScope, family: str) -> str:
    """Validate and return the numeric slot encoded by one identifier."""
    code = re.sub(r"[^a-z0-9]", "", family)[:4].upper()
    identity = re.fullmatch(rf"{scope.prefix}-{code}([0-9]{{4}})", identifier)
    if identity is None:
        raise ValueError(
            f"Rule ID {identifier} does not match the {scope} scope and {family} family "
            f"declared by {module}"
        )
    return identity.group(1)


RuleDefinition.model_rebuild(
    _types_namespace={
        "FixDefinition": FixDefinition,
        "RuleDocumentation": RuleDocumentation,
        "RuleIdentity": RuleIdentity,
        "RulePolicy": RulePolicy,
    }
)
