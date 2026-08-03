from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .clone import CloneCall
    from .lifetimes import LifetimeAnnotation, StaticLifetime


class RustSurfaceFact(Fact):
    """Describe the borrowing, pinning, and copying surface of one Rust module."""

    annotations: list[LifetimeAnnotation] = []
    pins: list[StaticLifetime] = []
    clones: list[CloneCall] = []
