from typing import TYPE_CHECKING

from patos import FrozenModel

if TYPE_CHECKING:
    from ..impacts import ImpactSet


class ImpactText(FrozenModel):
    """Render a change impact set with nearest modules first."""

    indent: str = "  "

    def render(self, projection: ImpactSet) -> str:
        """State what changed, what is unresolved, and what reaches the change."""
        width = max((len(item.module) for item in projection.reached), default=0)
        lines = [
            f"{len(projection.changed)} changed, {len(projection.reached)} modules "
            f"reach them through imports",
            "",
            *(f"{self.indent}changed {module}" for module in projection.changed),
            *(f"{self.indent}unresolved {path}" for path in projection.unresolved),
            "",
            "hops  module",
            *(
                f"{item.distance:>4}  {item.module.ljust(width)}  {item.path}"
                for item in projection.reached
            ),
        ]
        return "\n".join(lines)
