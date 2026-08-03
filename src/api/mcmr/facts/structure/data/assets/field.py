from patos import FrozenModel


class DataField(FrozenModel):
    """Retain one catalog field and its documented type."""

    name: str
    data_type: str
    description: str = ""
