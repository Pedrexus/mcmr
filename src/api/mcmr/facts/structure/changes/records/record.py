from .groups import ChangeRecordFields


class ChangeRecord(ChangeRecordFields):
    """Retain one change and the review policy applied by its merge path."""

    verification_evidence: list[str] = []
