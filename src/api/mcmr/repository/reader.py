from typing import TYPE_CHECKING

from ..kernel import KernelClient
from ..kernel.protocol import RepositoryGraph

if TYPE_CHECKING:
    from ..kernel.protocol import KernelArgument


class GraphReader(KernelClient):
    """Ask the analysis kernel for the repository graph rather than fact streams."""

    def read(self) -> RepositoryGraph:
        """Run the kernel over the repository and return the graph it built."""
        request: dict[str, KernelArgument] = {"families": [], "graph": True}
        return RepositoryGraph.model_validate(self.ask(request).graph)
