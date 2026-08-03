from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .match import AuthorshipMatch


class AuthorshipSignalFact(Fact):
    """Describe exact style matches from an explicitly enabled analyzer."""

    external_evidence = True
    matches: list[AuthorshipMatch] = []
