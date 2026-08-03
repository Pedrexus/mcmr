from typing import Annotated

from patos import FrozenModel
from pydantic import Field, NonNegativeFloat

from ..cases import ContextualTrial
from .backend import BackendProfile


class ProfileExperiment(FrozenModel):
    """Summarize all labeled trials for one backend profile."""

    profile: BackendProfile
    trials: Annotated[list[ContextualTrial], Field(min_length=1)]
    elapsed_seconds: NonNegativeFloat

    @property
    def accuracy(self) -> float:
        """Return the exact-match share over all labeled cases."""
        return 100 * self.passed / len(self.trials)

    @property
    def cached_input_tokens(self) -> int:
        """Return all cached input tokens reported by candidate model turns."""
        return sum(
            trial.provenance.cached_input_tokens
            for trial in self.trials
            if trial.provenance is not None
        )

    @property
    def input_tokens(self) -> int:
        """Return all input tokens reported by candidate model turns."""
        return sum(
            trial.provenance.input_tokens for trial in self.trials if trial.provenance is not None
        )

    @property
    def model_calls(self) -> int:
        """Return the number of candidate model turns with reported provenance."""
        return sum(trial.provenance is not None for trial in self.trials)

    @property
    def output_tokens(self) -> int:
        """Return all output tokens reported by candidate model turns."""
        return sum(
            trial.provenance.output_tokens for trial in self.trials if trial.provenance is not None
        )

    @property
    def passed(self) -> int:
        """Return the number of exact labeled answers this profile reproduced."""
        return sum(trial.passed for trial in self.trials)

    @property
    def reasoning_characters(self) -> int:
        """Return retained explanation length when token telemetry is unavailable."""
        return sum(len(reason) for trial in self.trials for reason in trial.reasoning)

    @property
    def reasoning_tokens(self) -> int:
        """Return all reasoning tokens reported by candidate model turns."""
        return sum(
            trial.provenance.reasoning_tokens
            for trial in self.trials
            if trial.provenance is not None
        )
