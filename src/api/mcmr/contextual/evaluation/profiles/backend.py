from typing import ClassVar, Self

from patos import FrozenModel

from ....domain.primitives import NonEmptyStr
from ....execution import ClassificationBackend
from ....project import ContextBackend, ContextualConfiguration


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

    def build(self, base: ContextualConfiguration, workers: int) -> ClassificationBackend:
        """Instantiate this profile through the shared Patos backend registry."""
        configured = base.model_copy(
            update={
                "backend": self.backend,
                "model": self.model,
                "reasoning_effort": self.reasoning_effort,
            }
        )
        backend = ClassificationBackend.find(str(self.backend))
        instance = backend.model_validate(configured, from_attributes=True)
        return instance.model_copy(update={"workers": workers})
