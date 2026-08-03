from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .route import Route


class RouteFact(Fact):
    """Describe every route a repository declares and references."""

    frameworks: list[str] = []
    routes: list[Route] = []
