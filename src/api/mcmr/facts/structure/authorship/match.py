from typing import TYPE_CHECKING

from .groups import AuthorshipFields

if TYPE_CHECKING:
    from pydantic import NonNegativeFloat

    from ....domain.primitives import NonEmptyStr
    from ...foundation import SourceSpan


class AuthorshipMatch(AuthorshipFields):
    """Retain one external analyzer match without inferring authorship."""

    matched_text: NonEmptyStr
    span: SourceSpan
    relative_likelihood: NonNegativeFloat | None = None
    is_eligible: bool = True
