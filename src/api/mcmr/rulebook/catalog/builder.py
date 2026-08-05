import inspect
import re
from functools import cached_property
from typing import TYPE_CHECKING

from patos import FrozenModel, Runtime
from pydantic import TypeAdapter

from ...domain.contracts import (
    RuleContract,
    RuleScope,
    output_contract,
)
from .contracts import (
    FixDefinition,
    RuleDefinition,
    RuleDocumentation,
    RuleIdentity,
    parse_identity,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def resolve_languages(
    rule_id: str, scope: RuleScope, stated: Mapping[str, set[str]]
) -> dict[str, set[str]]:
    """Resolve path scope and annotated table language constraints once."""
    automatic = set() if scope is RuleScope.GENERAL else {str(scope)}
    resolved: dict[str, set[str]] = {}
    for index, (name, languages) in enumerate(stated.items()):
        if str(RuleScope.GENERAL) in languages:
            raise TypeError(f"{rule_id} table {name} cannot name general as a language")
        inherited = automatic if index == 0 else set()
        if inherited and languages and languages != inherited:
            expected = next(iter(automatic))
            raise TypeError(f"{rule_id} table {name} must use its {expected} scope")
        resolved[name] = languages or inherited
    return resolved


class RuleDefinitionBuilder(FrozenModel):
    """Build one validated definition from a decorated rule contract."""

    candidate: Runtime[RuleContract]

    @cached_property
    def contract_fields(self) -> dict[str, object]:
        """Return output and policy fields validated as one contract."""
        output, unit, categories = output_contract(self.candidate.hints["return"])
        return {
            "output": output,
            "unit": unit,
            "categories": categories,
            "policy": self.candidate.policy,
        }

    @cached_property
    def descriptive_fields(self) -> dict[str, object]:
        """Return dependency, setting, documentation, and repair fields."""
        languages = resolve_languages(
            self.candidate.id, self.identity.scope, self.candidate.table_languages
        )
        return {
            "tables": [table.__name__ for _, table in self.candidate.tables],
            "languages": {name: sorted(values) for name, values in languages.items() if values},
            "settings": self.settings(),
            "documentation": self._documentation(self.candidate.raw_documentation),
            "fixes": self.fixes(),
        }

    @cached_property
    def identity(self) -> RuleIdentity:
        """Return the rule identity derived from its identifier and module path."""
        scope, lane, family, _ = parse_identity(self.candidate.module, self.candidate.id)
        return RuleIdentity(
            id=self.candidate.id,
            callable=self.candidate.callable_path,
            scope=scope,
            lane=lane,
            external=any(table.external_evidence for _, table in self.candidate.tables),
            family=family,
            fact=self.candidate.primary_family.__name__,
        )

    @cached_property
    def parameters(self) -> list[inspect.Parameter]:
        """Return the candidate signature parameters after proving an input exists."""
        parameters = list(self.candidate.signature.parameters.values())
        if not parameters:
            raise TypeError(f"{self.candidate.id} needs at least one Table input")
        return parameters

    def build(self) -> RuleDefinition:
        """Validate the table and query boundaries, then return one definition."""
        self._parameters(self.candidate.id, self.parameters, self.candidate.hints)
        if not self.candidate.table_native:
            raise TypeError(f"{self.candidate.id} must receive at least one typed Table")
        if not self.candidate.query_native:
            raise TypeError(f"{self.candidate.id} must return one RuleQuery or ModelQuery")
        fields = {"identity": self.identity} | self.contract_fields | self.descriptive_fields
        return RuleDefinition.model_validate(fields)

    def fixes(self) -> list[FixDefinition]:
        """Return the query repair contract when one is declared."""
        if self.candidate.query_fix_safety is None:
            return []
        return [
            FixDefinition(
                name="query",
                callable=f"{self.candidate.callable_path}.query_fix",
                is_default=True,
                safety=self.candidate.query_fix_safety,
            )
        ]

    def settings(self) -> dict[str, str]:
        """Encode keyword settings from their source defaults."""
        return {
            parameter.name: (
                "{" + ", ".join(map(repr, sorted(parameter.default))) + "}"
                if isinstance(parameter.default, set)
                else repr(parameter.default)
            )
            for parameter in self.parameters
            if parameter.default is not inspect.Parameter.empty
        }

    @staticmethod
    def _default(rule_id: str, parameter: inspect.Parameter, annotation: type) -> None:
        """Validate one present default against its constrained annotation."""
        if parameter.default is inspect.Parameter.empty:
            return
        if type(parameter.default) in {int, float} and annotation in {int, float}:
            raise TypeError(
                f"{rule_id} numeric setting {parameter.name} needs a constrained annotation"
            )
        TypeAdapter(annotation).validate_python(parameter.default)

    @staticmethod
    def _documentation(raw: str) -> RuleDocumentation:
        """Parse and validate the established reStructuredText rule sections."""
        cleaned = inspect.cleandoc(raw)
        headings = ["Definition", "Evidence", "Exceptions", "Examples", "References"]
        positions = {
            heading: match.start()
            for heading in headings
            if (match := re.search(rf"(?m)^[ \t]*{heading}\n[ \t]*-+\n", cleaned)) is not None
        }
        for required in ("Definition", "Examples", "References"):
            if required not in positions:
                raise ValueError(f"Rule documentation needs a {required} section")
        ordered = sorted(positions.items(), key=lambda item: item[1])
        sections = {
            heading: inspect.cleandoc(
                cleaned[
                    cleaned.find("\n", cleaned.find("\n", start) + 1) + 1 : (
                        ordered[index + 1][1] if index + 1 < len(ordered) else len(cleaned)
                    )
                ]
            )
            for index, (heading, start) in enumerate(ordered)
        }
        return RuleDocumentation(
            summary=cleaned[: min(positions.values())].strip(),
            definition=sections["Definition"],
            evidence=sections.get("Evidence", ""),
            exceptions=sections.get("Exceptions", ""),
            examples=sections["Examples"],
            references=[
                line.strip() for line in sections["References"].splitlines() if line.strip()
            ],
        )

    @staticmethod
    def _parameter(
        rule_id: str,
        parameter: inspect.Parameter,
        hints: Mapping[str, type],
    ) -> None:
        """Validate one declared parameter and its default."""
        if parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            raise TypeError(f"{rule_id} cannot use variadic input {parameter.name}")
        if (
            parameter.default is not inspect.Parameter.empty
            and parameter.kind is not inspect.Parameter.KEYWORD_ONLY
        ):
            raise TypeError(f"{rule_id} setting {parameter.name} must be keyword-only")
        if parameter.name not in hints:
            raise TypeError(f"{rule_id} input {parameter.name} needs an annotation")
        RuleDefinitionBuilder._default(rule_id, parameter, hints[parameter.name])

    @staticmethod
    def _parameters(
        rule_id: str,
        parameters: Sequence[inspect.Parameter],
        hints: Mapping[str, type],
    ) -> None:
        """Require explicit inputs and checked keyword-only settings."""
        for parameter in parameters:
            RuleDefinitionBuilder._parameter(rule_id, parameter, hints)
