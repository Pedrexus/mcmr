from patos import FrozenModel
from pydantic import NonNegativeInt


class LiteralTestLoop(FrozenModel):
    """Retain one test-owned loop over literal cases."""

    case_count: NonNegativeInt
    owns_assertion: bool
