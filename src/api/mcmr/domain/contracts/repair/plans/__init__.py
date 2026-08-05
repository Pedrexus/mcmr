from .contracts import Choice, Edit, Finding, FixPlan, Observation, SourceRewrite
from .rewrites import Inline, Move, Remove, RemoveDirectory, Rename, Replace, Unwrap

Finding.model_rebuild(_types_namespace={"Choice": Choice, "Edit": Edit})
Observation.model_rebuild(_types_namespace={"Finding": Finding})

__all__ = [
    "Choice",
    "Edit",
    "Finding",
    "FixPlan",
    "Observation",
    "Inline",
    "Move",
    "Remove",
    "RemoveDirectory",
    "Rename",
    "Replace",
    "SourceRewrite",
    "Unwrap",
]
