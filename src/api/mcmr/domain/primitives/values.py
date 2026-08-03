from enum import StrEnum, auto

type RuleValue = bool | int | float | str
type RuleSetting = RuleValue | list[str] | set[str]


class Unit(StrEnum):
    """Identify the scale carried by one numeric rule value."""

    COUNT = auto()
    PERCENTAGE = auto()
