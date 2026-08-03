from typing import Annotated

from patos import FrozenModel
from pydantic import Field

from ...domain.primitives import NonEmptyStr

type Ratio = Annotated[float, Field(ge=0.0, le=1.0)]


class Evidence(FrozenModel):
    """Retain one provider claim supporting a named rule measurement."""

    signal: NonEmptyStr
    detail: NonEmptyStr
    source: NonEmptyStr
    confidence: Ratio = 1.0
