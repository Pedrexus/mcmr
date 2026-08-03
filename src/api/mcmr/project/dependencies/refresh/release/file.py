from patos import FrozenModel
from pydantic import AwareDatetime


class ReleaseFile(FrozenModel):
    """Relevant state of one exact published distribution file."""

    upload_time_iso_8601: AwareDatetime
    yanked: bool = False
