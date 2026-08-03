from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import JsonValue, StrictBool, model_validator

from ....domain.contracts import RuleSetting
from ....domain.policy import RulePolicy

if TYPE_CHECKING:
    from collections.abc import Mapping


class RuleConfiguration(FrozenModel):
    """Hold the settings and policy one project states for one exact rule."""

    enabled: StrictBool = True
    exclude: list[str] = []
    settings: dict[str, RuleSetting] = {}
    policy: RulePolicy | None = None

    @model_validator(mode="before")
    @classmethod
    def collect_settings(cls, value: JsonValue) -> JsonValue:
        """Accept rule settings beside the reserved configuration fields."""
        if not isinstance(value, dict):
            return value
        nested = value.get("settings", {})
        if not isinstance(nested, dict):
            return value
        direct = cls._direct_settings(value)
        if repeated := set(nested) & set(direct):
            raise ValueError(f"Rule settings repeat {', '.join(sorted(repeated))}")
        return {
            "enabled": value.get("enabled", True),
            "exclude": value.get("exclude", []),
            "settings": {**nested, **direct},
            "policy": value.get("policy"),
        }

    @staticmethod
    def _direct_settings(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
        """Return fields outside the reserved rule configuration surface."""
        reserved = {"enabled", "exclude", "policy", "settings"}
        return {name: setting for name, setting in value.items() if name not in reserved}
