from collections.abc import Mapping
from pathlib import Path

from patos import FrozenModel
from pydantic import JsonValue


class PublicationContext(FrozenModel):
    """Name the assets one completed run judged and where its result can be read."""

    repository: Path
    settings: Mapping[str, JsonValue] = {}
    subjects: list[str] = []
    label: str = "MCMR policy run"
