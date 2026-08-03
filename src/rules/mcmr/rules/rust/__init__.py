from .deterministic.lifetimes.r0001 import elidable_lifetime_annotation
from .deterministic.lifetimes.r0002 import demanded_static_lifetime
from .deterministic.lifetimes.r0003 import lifetime_annotation_count
from .deterministic.ownership.r0001 import clone_inside_loop
from .deterministic.ownership.r0002 import clone_call_count

__all__ = [
    "clone_call_count",
    "clone_inside_loop",
    "demanded_static_lifetime",
    "elidable_lifetime_annotation",
    "lifetime_annotation_count",
]
