import inspect
import re
from functools import cached_property
from types import ModuleType
from typing import TYPE_CHECKING

from .bases import FrozenFlexModel
from .models import (
    Fix,
    FixContract,
    FixDefinition,
    Rule,
    RuleContract,
    RuleDefinition,
    RuleDocumentation,
    RuleLane,
    RuleScope,
    fact_type,
    output_contract,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


class Catalog(FrozenFlexModel):
    """Validate decorated rules and fixes without executing a backend."""

    modules: list[ModuleType]

    @cached_property
    def rules(self) -> list[RuleContract]:
        """Return every decorated rule found in the supplied modules."""
        return [
            candidate
            for module in self.modules
            for _, candidate in inspect.getmembers(module)
            if isinstance(candidate, Rule)
        ]

    @cached_property
    def fixes(self) -> list[FixContract]:
        """Return every decorated fix found in the supplied modules."""
        return [
            candidate
            for module in self.modules
            for _, candidate in inspect.getmembers(module)
            if isinstance(candidate, Fix)
        ]

    @cached_property
    def definitions(self) -> list[RuleDefinition]:
        """Return every validated rule in stable identity order."""
        definitions = [self.definition(candidate, self.fixes) for candidate in self.rules]
        ids = [definition.id for definition in definitions]
        if duplicate := next((item for item in ids if ids.count(item) > 1), ""):
            raise ValueError(f"Duplicate rule ID {duplicate}")
        return sorted(definitions, key=lambda item: item.id)

    def definition(self, candidate: RuleContract, fixes: Sequence[FixContract]) -> RuleDefinition:
        """Build one definition from its source identity and typed signature."""
        scope, lane, family, number = self.identity(candidate.module)
        code = re.sub(r"[^a-z0-9]", "", family)[:4].upper()
        rule_id = f"{scope.prefix}-{code}{number}"
        signature = candidate.signature
        parameters = list(signature.parameters.values())
        if not parameters:
            raise TypeError(f"{rule_id} needs one Fact input")
        hints = candidate.hints
        fact = fact_type(hints[parameters[0].name])
        self.validate_parameters(rule_id, parameters)
        output, unit, categories = output_contract(hints["return"])
        attached = [item for item in fixes if item.rule_callable == candidate.callable_path]
        return RuleDefinition(
            id=rule_id,
            callable=candidate.callable_path,
            scope=scope,
            lane=lane,
            family=family,
            fact=fact.__name__,
            output=output,
            unit=unit,
            categories=categories,
            settings=self.settings(parameters),
            documentation=self.documentation(candidate.raw_documentation),
            fixes=self.fix_definitions(rule_id, signature, attached),
        )

    @staticmethod
    def identity(module: str) -> tuple[RuleScope, RuleLane, str, str]:
        """Derive rule scope, execution lane, family, and slot from its path.

        The lane owns the leading digit of the slot, so two lanes sharing a scope and a family can
        never mint the same identifier. A file numbered against its own lane is rejected here
        rather than colliding with a rule somewhere else in the tree.
        """
        scopes = "|".join(RuleScope)
        lanes = "|".join(RuleLane)
        match = re.fullmatch(
            rf"mcmr\.rules\.({scopes})\.({lanes})\.([a-z][a-z0-9_]*)\.r([0-9]{{4}})",
            module,
        )
        if match is None:
            raise ValueError(f"Rule module {module} does not follow the MCMR rule path")
        lane = RuleLane(match.group(2))
        slot = match.group(4)
        if not slot.startswith(lane.slot):
            raise ValueError(
                f"Rule module {module} is in the {lane} lane, whose numbers begin with "
                f"{lane.slot}, so r{slot} belongs to another lane"
            )
        return RuleScope(match.group(1)), lane, match.group(3), slot

    @staticmethod
    def validate_parameters(rule_id: str, parameters: list[inspect.Parameter]) -> None:
        """Require explicit injected inputs and keyword-only settings."""
        for parameter in parameters:
            if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
                raise TypeError(f"{rule_id} cannot use variadic input {parameter.name}")
            if (
                parameter.default is not inspect.Parameter.empty
                and parameter.kind is not inspect.Parameter.KEYWORD_ONLY
            ):
                raise TypeError(f"{rule_id} setting {parameter.name} must be keyword-only")

    @staticmethod
    def settings(parameters: list[inspect.Parameter]) -> dict[str, str]:
        """Encode keyword settings from their source defaults."""
        return {
            parameter.name: repr(parameter.default)
            for parameter in parameters
            if parameter.default is not inspect.Parameter.empty
        }

    @staticmethod
    def documentation(raw: str) -> RuleDocumentation:
        """Parse the established reStructuredText rule sections."""
        raw = inspect.cleandoc(raw)
        headings = ["Definition", "Evidence", "Exceptions", "Examples", "References"]
        positions = {
            heading: match.start()
            for heading in headings
            if (match := re.search(rf"(?m)^[ \t]*{heading}\n[ \t]*-+\n", raw)) is not None
        }
        for required in ("Definition", "Examples", "References"):
            if required not in positions:
                raise ValueError(f"Rule documentation needs a {required} section")
        first = min(positions.values())
        summary = raw[:first].strip()
        sections: dict[str, str] = {}
        ordered = sorted(positions.items(), key=lambda item: item[1])
        for index, (heading, start) in enumerate(ordered):
            content_start = raw.find("\n", raw.find("\n", start) + 1) + 1
            content_end = ordered[index + 1][1] if index + 1 < len(ordered) else len(raw)
            sections[heading] = inspect.cleandoc(raw[content_start:content_end])
        return RuleDocumentation(
            summary=summary,
            definition=sections["Definition"],
            evidence=sections.get("Evidence", ""),
            exceptions=sections.get("Exceptions", ""),
            examples=sections["Examples"],
            references=[
                line.strip() for line in sections["References"].splitlines() if line.strip()
            ],
        )

    @staticmethod
    def fix_definitions(
        rule_id: str,
        rule_signature: inspect.Signature,
        fixes: Sequence[FixContract],
    ) -> list[FixDefinition]:
        """Validate compatible fix signatures and resolve one optional default."""
        for fix in fixes:
            if list(fix.signature.parameters.values()) != list(rule_signature.parameters.values()):
                raise TypeError(f"{fix.qualname} inputs must match {rule_id}")
        explicit = [fix for fix in fixes if fix.is_default]
        if len(explicit) > 1:
            raise ValueError(f"{rule_id} has multiple default fixes")
        inferred = fixes[0] if len(fixes) == 1 and not explicit else None
        return [
            FixDefinition(
                name=fix.qualname.rsplit(".", 1)[-1],
                callable=f"{fix.module}.{fix.qualname}",
                is_default=fix.is_default or fix is inferred,
                safety=fix.safety,
            )
            for fix in fixes
        ]
