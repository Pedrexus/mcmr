from enum import StrEnum, auto


class RepairMode(StrEnum):
    """Choose whether one check reports, previews repairs, or applies verified repairs."""

    NONE = auto()
    PREVIEW = auto()
    APPLY = auto()
    APPLY_REVIEW = "apply-review"
