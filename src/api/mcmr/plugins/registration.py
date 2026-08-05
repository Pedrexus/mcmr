from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..execution.providers import FactProvider


def provider[Provider: FactProvider](factory: type[Provider]) -> type[Provider]:
    """Mark a zero-argument external fact provider factory for plugin discovery."""
    return factory
