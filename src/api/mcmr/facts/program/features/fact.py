from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .flag import FeatureFlag


class FeatureFlagFact(Fact):
    """Describe one feature flag and its lifecycle evidence."""

    flags: list[FeatureFlag] = []
