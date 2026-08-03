import inspect
import re
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from ...domain.contracts import (
    RuleDocumentation,
    RuleId,
    RuleLane,
    RuleScope,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


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


def parse_documentation(raw: str) -> RuleDocumentation:
    """Parse and validate the established reStructuredText rule sections."""
    cleaned = inspect.cleandoc(raw)
    positions = _documentation_positions(cleaned)
    for required in ("Definition", "Examples", "References"):
        if required not in positions:
            raise ValueError(f"Rule documentation needs a {required} section")
    sections = _documentation_sections(cleaned, positions)
    return RuleDocumentation(
        summary=cleaned[: min(positions.values())].strip(),
        definition=sections["Definition"],
        evidence=sections.get("Evidence", ""),
        exceptions=sections.get("Exceptions", ""),
        examples=sections["Examples"],
        references=[line.strip() for line in sections["References"].splitlines() if line.strip()],
    )


def validate_parameters(
    rule_id: str, parameters: Sequence[inspect.Parameter], hints: Mapping[str, type]
) -> None:
    """Require explicit inputs and checked keyword-only settings."""
    for parameter in parameters:
        _validate_parameter(rule_id, parameter, hints)


def _content_start(cleaned: str, start: int) -> int:
    """Return the first character after one heading underline."""
    return cleaned.find("\n", cleaned.find("\n", start) + 1) + 1


def _documentation_positions(cleaned: str) -> dict[str, int]:
    """Locate every recognized section heading."""
    headings = ["Definition", "Evidence", "Exceptions", "Examples", "References"]
    return {
        heading: match.start()
        for heading in headings
        if (match := re.search(rf"(?m)^[ \t]*{heading}\n[ \t]*-+\n", cleaned)) is not None
    }


def _documentation_sections(cleaned: str, positions: Mapping[str, int]) -> dict[str, str]:
    """Return normalized content under each recognized heading."""
    ordered = sorted(positions.items(), key=lambda item: item[1])
    return {
        heading: inspect.cleandoc(
            cleaned[_content_start(cleaned, start) : _section_end(index, ordered, cleaned)]
        )
        for index, (heading, start) in enumerate(ordered)
    }


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


def _section_end(index: int, ordered: Sequence[tuple[str, int]], cleaned: str) -> int:
    """Return where one documentation section ends."""
    return ordered[index + 1][1] if index + 1 < len(ordered) else len(cleaned)


def _validate_default(rule_id: str, parameter: inspect.Parameter, annotation: type) -> None:
    """Validate one present default against its constrained annotation."""
    if type(parameter.default) in {int, float} and annotation in {int, float}:
        raise TypeError(
            f"{rule_id} numeric setting {parameter.name} needs a constrained annotation"
        )
    TypeAdapter(annotation).validate_python(parameter.default)


def _validate_parameter(
    rule_id: str, parameter: inspect.Parameter, hints: Mapping[str, type]
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
    if parameter.default is not inspect.Parameter.empty:
        _validate_default(rule_id, parameter, hints[parameter.name])
