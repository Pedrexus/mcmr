from typing import Annotated

from patos import FrozenModel
from pydantic import Field

from ..profiles import ProfileExperiment


class ContextualExperimentReport(FrozenModel):
    """Compare profiles and recommend the smallest exact one per rule."""

    profiles: Annotated[list[ProfileExperiment], Field(min_length=1)]

    @property
    def recommendations(self) -> dict[str, str]:
        """Return the first profile passing every labeled case for each rule."""
        rules = {trial.rule for result in self.profiles for trial in result.trials}
        return {
            rule: profile
            for rule in sorted(rules)
            if (profile := self.passing_profile(rule)) is not None
        }

    @property
    def unresolved(self) -> list[str]:
        """Return rules no tested profile reproduced on every reviewed case."""
        rules = {trial.rule for result in self.profiles for trial in result.trials}
        return sorted(rules - self.recommendations.keys())

    def passing_profile(self, rule: str) -> str | None:
        """Return the first profile passing every labeled case for one rule."""
        for result in self.profiles:
            trials = [trial for trial in result.trials if trial.rule == rule]
            if trials and all(trial.passed for trial in trials):
                return result.profile.name
        return None
