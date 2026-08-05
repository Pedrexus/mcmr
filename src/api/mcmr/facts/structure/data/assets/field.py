from patos import FrozenModel


class DataField(FrozenModel):
    """Retain one catalog field, its documented type, and its governance labels."""

    name: str
    data_type: str
    description: str = ""
    tags: list[str] = []
    glossary_terms: list[str] = []
