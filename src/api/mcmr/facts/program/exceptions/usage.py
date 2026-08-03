from patos import FrozenModel


class ExceptionUsage(FrozenModel):
    """Retain one project exception and its ordinary importing modules."""

    name: str
    defining_module: str
    importing_modules: list[str] = []
