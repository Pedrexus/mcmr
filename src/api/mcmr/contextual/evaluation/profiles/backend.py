from typing import TYPE_CHECKING, ClassVar, Self

from patos import FrozenModel

from ....domain.primitives import NonEmptyStr
from ....execution import ClassificationBackend
from ....project import ContextBackend, ContextualConfiguration

if TYPE_CHECKING:
    from pydantic import PositiveInt


class BackendProfile(FrozenModel):
    """Name one ordered contextual backend and model operating point."""

    name: NonEmptyStr
    backend: ContextBackend
    model: NonEmptyStr
    reasoning_effort: NonEmptyStr

    routine_profiles: ClassVar[tuple[tuple[str, ContextBackend, str, str], ...]] = (
        ("gliner2-base", ContextBackend.GLINER2, "fastino/gliner2-base-v1", "none"),
        ("luna-none", ContextBackend.CODEX, "gpt-5.6-luna", "none"),
        ("luna-low", ContextBackend.CODEX, "gpt-5.6-luna", "low"),
        ("luna-medium", ContextBackend.CODEX, "gpt-5.6-luna", "medium"),
        ("luna-high", ContextBackend.CODEX, "gpt-5.6-luna", "high"),
        ("terra-medium", ContextBackend.CODEX, "gpt-5.6-terra", "medium"),
    )

    @classmethod
    def routine(cls, *, include_sol: bool = False) -> list[Self]:
        """Return the smallest-first model matrix used for routine selection."""
        profiles = [
            cls(name=name, backend=backend, model=model, reasoning_effort=effort)
            for name, backend, model, effort in cls.routine_profiles
        ]
        if include_sol:
            profiles.append(
                cls(
                    name="sol-medium",
                    backend=ContextBackend.CODEX,
                    model="gpt-5.6-sol",
                    reasoning_effort="medium",
                )
            )
        return profiles

    def build(
        self,
        base: ContextualConfiguration,
        workers: PositiveInt | None = None,
    ) -> ClassificationBackend:
        """Instantiate this profile through the shared Patos backend registry.

        base: project settings whose declared fields this backend accepts.
        workers: maximum isolated model operations, or the backend default when absent.
        """
        backend = ClassificationBackend.find(str(self.backend))
        configured = base.model_copy(
            update={"model": self.model, "reasoning_effort": self.reasoning_effort}
        )
        settings = {
            name: value
            for name, value in configured.model_dump().items()
            if name in backend.model_fields and value is not None
        }
        return backend.model_validate(settings | ({"workers": workers} if workers else {}))
