from patos import FrozenModel


class TestCaseGroup(FrozenModel):
    """Retain sibling tests with the same normalized nonliteral syntax."""

    normalized_syntax: str
    literal_vectors: list[list[str]] = []
