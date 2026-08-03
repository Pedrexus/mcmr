from typing import Protocol


class Function[**P, Result](Protocol):
    """Expose the callable and source identity every declared function provides."""

    __module__: str
    __qualname__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Result: ...
