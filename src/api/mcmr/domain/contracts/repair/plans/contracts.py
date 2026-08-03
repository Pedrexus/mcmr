from typing import Annotated, Literal

from patos import FrozenModel
from pydantic import Field

from .....facts import SourceSpan
from ....primitives import NonEmptyStr
from ...primitives import FixSafety
from ..evidence import Measurement, ModelProvenance
from .rewrites import Inline, Move, Remove, RemoveDirectory, Rename, Replace, Unwrap

type SourceRewrite = Annotated[
    Remove | RemoveDirectory | Replace | Move | Unwrap | Rename | Inline,
    Field(discriminator="kind"),
]


class _RepairContracts:
    """Own complete plans and the findings that may offer them."""

    class FixPlan(FrozenModel):
        """Describe one nonempty atomic fix as an ordered rewrite program."""

        summary: NonEmptyStr
        rewrites: list[SourceRewrite] = Field(min_length=1)

        @property
        def spans(self) -> list[SourceSpan]:
            """Return every span this plan edits in rewrite order."""
            return [span for rewrite in self.rewrites for span in rewrite.spans]

    class Choice(FrozenModel):
        """Name the decision a reader must make when no edit is proven."""

        kind: Literal["choice"] = "choice"
        question: NonEmptyStr
        options: list[NonEmptyStr] = []

        @property
        def summary(self) -> str:
            """Return the question with its named answers when present."""
            return (
                f"{self.question} ({' or '.join(self.options)})" if self.options else self.question
            )

    class Edit(FrozenModel):
        """Close one finding by applying a validated rewrite plan."""

        kind: Literal["edit"] = "edit"
        plan: _RepairContracts.FixPlan
        safety: FixSafety = FixSafety.SAFE

        @property
        def summary(self) -> str:
            """Return what the plan says it does."""
            return self.plan.summary

    class Finding(FrozenModel):
        """Describe one actionable rule finding and its evidence."""

        message: NonEmptyStr
        span: SourceSpan
        measurements: list[Measurement] = []
        evidence: list[str] = []
        provenance: ModelProvenance | None = None
        repair: (
            Annotated[
                _RepairContracts.Edit | _RepairContracts.Choice,
                Field(discriminator="kind"),
            ]
            | None
        ) = None


Choice = _RepairContracts.Choice
Edit = _RepairContracts.Edit
Finding = _RepairContracts.Finding
FixPlan = _RepairContracts.FixPlan
