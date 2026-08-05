from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from patos import FrozenModel

from ....support import kernel_binary
from ...adapters import Oracle

if TYPE_CHECKING:
    from collections.abc import Mapping


class Trees(FrozenModel):
    """Write one fresh tree per generated example, under a directory pytest cleans up.

    A reading is cached by the tree it read, so a property that draws a new source has to write it
    somewhere nothing has been asked about yet. The number of trees already grown is read off the
    filesystem rather than counted, which keeps this frozen and keeps two properties sharing one
    directory from handing out the same name.
    """

    root: Path

    def grow(self, sources: Mapping[str, str]) -> Path:
        """Write one more generated tree and return it."""
        planted = self.root / f"tree{sum(1 for _ in self.root.iterdir())}"
        planted.mkdir()
        return written(planted, sources)


def written(root: Path, sources: Mapping[str, str]) -> Path:
    """Write one generated source per relative name and return the tree holding them."""
    for relative, source in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return root


needs_kernel = pytest.mark.skipif(
    not kernel_binary().exists(),
    reason="a differential oracle needs the kernel binary this checkout builds",
)


def needs(*tools: str) -> pytest.MarkDecorator:
    """Skip a case whose oracle is not installed here, naming which tool is missing.

    A skipped oracle proves nothing, so the reason names the tool rather than the case, and the
    suite's own summary is then the ledger of what could not be checked on this machine.
    """
    absent = sorted(tool for tool in tools if not Oracle.installed(tool))
    return pytest.mark.skipif(
        bool(absent), reason=f"the differential oracle needs {', '.join(absent)} installed"
    )
