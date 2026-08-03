from patos import FrozenModel


class KernelStreamBatch(FrozenModel):
    """Hold one family name beside its still-unparsed JSON facts."""

    family: str
    payload: str
