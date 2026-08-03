import subprocess
from pathlib import Path

import pytest

from mcmr.kernel import locate
from mcmr.repository import (
    GraphReader,
    RepositoryGraph,
)

_PACKAGE = Path(__file__).parents[2]

pytestmark = pytest.mark.skipif(
    not locate(_PACKAGE).exists(),
    reason="the diagram oracle needs the kernel binary this checkout builds",
)


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write one package both readers agree on, so a mismatch is a real disagreement.

    Everything here is stated in the source rather than inferred from it. An enum member, a
    dataclass field, and a base from the standard library all reach Pyreverse through inference
    that MCMR has no engine for, so a fixture holding one would be measuring the inference rather
    than the diagram. The nested class is here because both readers draw it as a box of its own
    rather than as a member of the class holding it, which is easy to get wrong.
    """
    root = tmp_path_factory.mktemp("diagrams")
    package = root / "shop"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(
        """class Item:
    label = "item"

    def __init__(self, name):
        self.name = name
        self._cost = 0
        self.__token = "opaque"

    @property
    def cost(self):
        return self._cost

    def render(self):
        return self.name

    class Tag:
        pass


class Priced:
    def price(self):
        return 0


class Book(Item, Priced):
    def render(self):
        return self.name.upper()

    def _shelve(self):
        return True
"""
    )
    (package / "api.py").write_text(
        """from .models import Book


class Shelf(Book):
    def stock(self):
        return self.render()
"""
    )
    return root


@pytest.fixture(scope="module")
def drawings(repository: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the real Pyreverse over the fixture and return where its dot files landed.

    The dot files go outside the repository so that the tree MCMR reads holds only the source
    Pyreverse read, which is what makes a difference between the two a real difference.
    """
    output = tmp_path_factory.mktemp("pyreverse")
    subprocess.run(
        [
            "python",
            "-m",
            "pylint.pyreverse.main",
            "--output",
            "dot",
            "--output-directory",
            str(output),
            "--filter-mode",
            "ALL",
            "shop",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    return output


@pytest.fixture(scope="module")
def graph(repository: Path) -> RepositoryGraph:
    """Return the repository graph the kernel builds over the same fixture."""
    return GraphReader(binary=locate(_PACKAGE), root=repository).read()
