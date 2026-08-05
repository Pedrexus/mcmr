import inspect
from functools import cached_property
from types import ModuleType
from typing import TYPE_CHECKING, ClassVar

from patos import FrozenModel
from pydantic import InstanceOf, TypeAdapter

from ...domain.contracts import (
    Rule,
    RuleContract,
    RuleId,
    RuleLane,
    RuleScope,
)
from .builder import RuleDefinitionBuilder, resolve_languages

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .contracts import RuleDefinition

from .contracts import parse_identity

_retired_rules: dict[str, str] = {
    "ALL-ARCH0004": "dependency hub quality requires contextual evidence rather than degree alone",
    "ALL-CLAS0002": (
        "module-local classes cannot satisfy both this rule and narrow public surfaces"
    ),
    "ALL-DATA0005": "blast radius is a report metric rather than a lint verdict",
    "ALL-DEPE1001": "dependency choice needs a candidate, requirements, and ownership evidence",
    "ALL-DEPE1002": "third-party alternatives need a documented external search provider",
    "ALL-DEPE1003": "capability fit needs requirements and candidate guarantees",
    "ALL-DEPE1004": "integration effort needs affected boundaries and estimates",
    "ALL-DEPE1005": "fork maintainability needs upstream and ownership evidence",
    "ALL-DOCU1001": "decision traceability needs decision records and their implementation links",
    "ALL-ERRO1001": "error context needs typed raises, handlers, messages, and propagation paths",
    "ALL-ERRO1002": "recovery boundaries need typed handlers, actions, and caller paths",
    "ALL-ERRO1003": "cleanup safety needs resource acquisition and release paths",
    "ALL-MIGR1001": "migration safety needs migration steps, schemas, and rollout evidence",
    "ALL-MIGR1002": "compatibility windows need versioned read and write contracts",
    "ALL-MIGR1003": "data verification needs migration checks and invariant evidence",
    "ALL-MIGR1004": "migration reversibility needs inverse steps or recovery evidence",
    "ALL-OBSE0001": "risk-to-signal judgment moved to the contextual lane",
    "ALL-OPER1001": "recovery readiness needs a concrete plan and exercise evidence",
    "ALL-OPER1002": "recovery objectives need declared targets and measured capability",
    "ALL-OPER1003": "recovery exercises need dated scenarios and observed outcomes",
    "ALL-OPER1004": "backup recoverability needs backup and restore evidence",
    "ALL-RELE1001": "release traceability needs artifact, source, and deployment provenance",
    "ALL-RELI1001": "retry safety needs operation effects, failure modes, and retry ownership",
    "ALL-RELI1002": "idempotency needs operation effects and replay protection evidence",
    "ALL-RELI1004": "retry eligibility needs failure class, replay effects, and ownership",
    "ALL-RELI1005": "retry budgets need deadlines, attempt limits, and capacity evidence",
    "ALL-RELI1006": "backoff quality needs retry configuration and timing evidence",
    "ALL-SECU0001": "threat-model completeness moved to the contextual lane",
    "ALL-SECU1001": "least privilege needs identities, grants, resources, and observed operations",
    "ALL-TEST0001": "the contextual test-strategy rule already owns this judgment",
    "ALL-WRIT0002": "segment coverage was neither actionable nor correctly directed",
    "ALL-WRIT0006": "detector output belongs in an external diagnostic report",
    "PY-MODE0002": "model placement needs contextual ownership and cycle evidence",
    "PY-TYPE0006": "typing placement needs contextual ownership and cycle evidence",
}


class Catalog(FrozenModel):
    """Validate decorated table rules without executing their queries."""

    modules: list[InstanceOf[ModuleType]]
    retirements: ClassVar[dict[str, str]] = _retired_rules

    @cached_property
    def definitions(self) -> list[RuleDefinition]:
        """Return every validated rule in stable identity order."""
        definitions = [self.definition(candidate) for candidate in self.rules]
        ids = [definition.id for definition in definitions]
        if duplicate := next((item for item in ids if ids.count(item) > 1), ""):
            raise ValueError(f"Duplicate rule ID {duplicate}")
        self.validate_numbering(definitions)
        return sorted(definitions, key=lambda item: item.id)

    @cached_property
    def rules(self) -> list[RuleContract]:
        """Return every decorated rule found in the supplied modules."""
        return [
            candidate
            for module in self.modules
            for _, candidate in inspect.getmembers(module)
            if isinstance(candidate, Rule)
        ]

    @staticmethod
    def identity(module: str, identifier: RuleId) -> tuple[RuleScope, RuleLane, str, str]:
        """Validate an explicit rule identity against its structural module path."""
        return parse_identity(module, identifier)

    @staticmethod
    def languages(
        rule_id: str,
        scope: RuleScope,
        stated: Mapping[str, set[str]],
    ) -> dict[str, set[str]]:
        """Resolve path scope and annotated table language constraints once."""
        return resolve_languages(rule_id, scope, stated)

    @staticmethod
    def validate_numbering(definitions: Sequence[RuleDefinition]) -> None:
        """Require every active or retired number in one rule family to appear in order."""
        Catalog._validate_numbering(definitions, Catalog.retirements)

    def definition(self, candidate: RuleContract) -> RuleDefinition:
        """Build one definition from its source identity and typed signature."""
        return RuleDefinitionBuilder(candidate=candidate).build()

    @staticmethod
    def _validate_group(
        members: Sequence[RuleDefinition],
        retirements: Mapping[str, str],
        *,
        family: str,
        lane_name: str,
    ) -> None:
        """Require one family and lane to occupy every slot from its first."""
        lane = RuleLane(lane_name)
        prefix = members[0].id[:-4]
        active = {int(item.id[-4:]): item.id for item in members}
        retired = {
            int(identifier[-4:]): identifier
            for identifier in retirements
            if identifier.startswith(prefix) and identifier[-4:].startswith(lane.slot)
        }
        for expected, actual in enumerate(sorted(active | retired), start=int(f"{lane.slot}001")):
            if actual != expected:
                identifier = (active | retired)[actual]
                raise ValueError(
                    f"Rule ID {identifier} leaves a numbering gap in the {family} family. "
                    f"The next available ID is {prefix}{expected:04d}"
                )

    @staticmethod
    def _validate_numbering(
        definitions: Sequence[RuleDefinition], retirements: Mapping[str, str]
    ) -> None:
        """Require every active or retired number in one family to appear in order."""
        active_ids = {definition.id for definition in definitions}
        if repeated := active_ids & retirements.keys():
            raise ValueError(f"Active rules repeat retired IDs {', '.join(sorted(repeated))}")
        Catalog._validate_retirements(retirements)
        groups: dict[tuple[str, str, str], list[RuleDefinition]] = {}
        for definition in definitions:
            key = (definition.scope, definition.lane, definition.family)
            groups.setdefault(key, []).append(definition)
        for (_, lane, family), members in groups.items():
            Catalog._validate_group(members, retirements, family=family, lane_name=lane)

    @staticmethod
    def _validate_retirements(retirements: Mapping[str, str]) -> None:
        """Require every retired identifier and explanation to be valid."""
        for identifier, reason in retirements.items():
            TypeAdapter(RuleId).validate_python(identifier)
            if not reason.strip():
                raise ValueError(f"Retired rule {identifier} needs a reason")
