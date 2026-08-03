from patos import FrozenModel
from pydantic import NonNegativeInt


class ByteEdit(FrozenModel):
    """Replace one half-open UTF-8 byte range with exact source bytes."""

    path: str
    start: NonNegativeInt
    end: NonNegativeInt
    replacement: bytes
