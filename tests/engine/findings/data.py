from patos import FrozenModel

# Which families answer for a whole repository rather than for one file, so the guard below can
# check the migrated slice still holds one of each.


_WIDE = {
    "CloneGroupFact",
    "DependencyComponentFact",
    "ModuleCouplingFact",
    "RepositoryHistoryFact",
}


class FindingStatement(FrozenModel):
    """The located finding and supporting detail one rule must state."""

    message: str
    location: str = ""
    measurements: dict[str, float] = {}
    rounded: dict[str, float] = {}
    repair: str = ""
    holds: str = ""
    silent: bool = False


# One project gives every migrated source rule something real to report.

# A finding must name the right thing in a file that also holds things it must ignore, so one
# project is stronger than one snippet per rule.
_FIXTURE: dict[str, str] = {
    "pyproject.toml": (
        """[project]
name = "shop"
requires-python = ">=3.14"

[tool.pytest.ini_options]
addopts = "-q --strict-config"
"""
    ),
    "shop/__init__.py": "",
    "shop/records.py": (
        '''from labels.wiring import label


class Receipt:
    """Hold what one order was charged."""

    total: int = 0
    currency: str = 'JPY'

    def total_text(self) -> str:
        """Return the amount as text."""
        return f"{self.total} {self.currency}"

    def __init__(self, total: int = 0) -> None:
        self.total = total

    def named(self) -> str:
        """Return the label this receipt prints under."""
        return label(self.total)
'''
    ),
    "shop/settings.py": (
        '''class Options:
    """Hold every knob one render takes."""

    width: int = 80
    indent: int = 2
'''
    ),
    "shop/service.py": (
        '''from json import dumps

from .records import Receipt
from .settings import Options


def describe(options: Options) -> str:
    """Render one receipt.

    Args:
        options: the knobs.
    """
    return f"{options.width}:{options.indent}"


def charge(first: Receipt, second: Receipt, label: str) -> int:
    """Add two receipts together."""
    t = first.total + second.total
    if label:
        return t
    return t


def readable(rows: list) -> bool:
    """Whether every row is short enough to print."""
    return all(len(row) < 80 for row in rows)


def helper(value: str) -> str:
    """Return the value unchanged."""
    return value


def render(receipt: Receipt) -> str:
    """Return one receipt as a line."""
    return helper(dumps({'total': receipt.total}))
'''
    ),
    "shop/types.py": (
        '''from pydantic import BaseModel


class OrderLine(BaseModel):
    """One line of one order."""

    total: int
'''
    ),
    "shop/api.py": (
        '''import textwrap

from .records import Receipt
from .types import OrderLine


def owed(line: OrderLine) -> int:
    """Return what one line owes."""
    return line.total


def submit(receipt: Receipt) -> str:
    """Submit one receipt and name what came back."""
    if receipt.total < 0:
        return "rejected"
    if receipt.total == 0:
        return "empty"
    return "placed"
'''
    ),
    "shop/left.py": (
        '''from .records import Receipt
from .types import OrderLine


def billed(line: OrderLine) -> int:
    """Return what one line was billed."""
    return line.total


def paid(receipt: Receipt) -> int:
    """Return what one receipt came to."""
    return receipt.total


def audit(rows: list[str]) -> int:
    """Count the rows that say something."""
    total = 0
    for row in rows:
        if not row:
            continue
        if row.startswith('#'):
            continue
        total = total + len(row) + len(row.strip()) + len(row.lstrip())
    return total
'''
    ),
    "shop/right.py": (
        '''def review(rows: list[str]) -> int:
    """Count the rows that say something."""
    total = 0
    for row in rows:
        if not row:
            continue
        if row.startswith('#'):
            continue
        total = total + len(row) + len(row.strip()) + len(row.lstrip())
    return total
'''
    ),
    "shop/prose.py": (
        '''def opened() -> str:
    """Return name. Return alias. Return label. Return title. Return brand. Return sign. Why."""
    return "shop"


def closed() -> str:
    """Return the name this shop closed under."""
    return "shop"


def widest() -> int:
    """Return the widest column this shop prints."""
    return 80


def narrowest() -> int:
    """Return the narrowest column this shop prints."""
    return 20


def counted() -> int:
    """Return how many receipts this shop holds."""
    return 0


def totalled() -> int:
    """Return what every receipt comes to together."""
    return 0


def explain() -> str:
    """Say what this module is here to do."""
    return "shop"
'''
    ),
    "labels/__init__.py": "",
    "labels/wiring.py": "from options import wiring as options\n\nlabel = options.label\n",
    "options/__init__.py": "",
    "options/wiring.py": "label = str\n",
    "buyer_one/__init__.py": "",
    "buyer_one/wiring.py": "from shop import records\n\nreceipt_type = records.Receipt\n",
    "buyer_two/__init__.py": "",
    "buyer_two/wiring.py": "from shop import records\n\nreceipt_type = records.Receipt\n",
    "buyer_three/__init__.py": "",
    "buyer_three/wiring.py": "from shop import records\n\nreceipt_type = records.Receipt\n",
}
# Worked examples that prove the full reporting contract across distinct rule shapes.
_EXEMPLARS: dict[str, str] = {
    "ALL-ARCH0002": "a count whose findings are the components of a repository-wide graph",
    "ALL-ARCH0003": "a count over a repository-wide fact",
    "ALL-CLAS0001": "a count over a per-file fact whose records carry their own range",
    "ALL-COMM0001": "a percentage naming the comment group and both sides of its normalization",
    "ALL-COMM0002": "a count whose findings are the source-shaped comment groups",
    "ALL-COMM0003": "a count whose findings are one per marker rather than one per group",
    "ALL-DUPL0003": "a count whose findings are one per record rather than one per fact",
    "ALL-DUPL0004": "a percentage over the same records",
    "ALL-FUNC0001": "a measure whose finding is the measurement itself",
    "ALL-FUNC0010": "a measure whose message changes shape when it counts nothing",
    "ALL-HIST0001": "a count over the recorded history of a repository",
    "ALL-MODU0001": "a measure over a whole module",
    "ALL-NAMI0001": "a count reading the syntax tree, located at the node it read",
    "ALL-PARA0001": "a count over the parameters one callable declares",
    "ALL-PARA0002": "a count over records the kernel had to learn to locate",
    "ALL-PARA0003": "a count whose findings locate every Boolean trapped in a position",
    "ALL-PARA0004": "a count whose one finding exposes the callable's whole Boolean state space",
    "ALL-REAC0002": "a count over the reach of what a module declares",
    "ALL-WRIT0005": "a percentage the rule takes the maximum of",
    "ALL-DESI1001": "the model lane, where the finding cites the claims the judgment read",
    "PY-COLL0001": "a bare Boolean rather than a declared occurrence",
    "PY-DOCU0001": "a Boolean whose findings say which of two shapes broke",
    "PY-IMPO0003": "an occurrence whose repair comes from the fix the rule already declares",
    "PY-NAMI0001": "an occurrence whose declared fix is a review rather than a safe edit",
    "PY-TEST0004": "a closed category",
    "RS-LIFE0001": "a count over records located by line inside a whole-module fact",
    "RS-LIFE0002": "a count whose records are the subset of a wider list that qualified",
    "RS-LIFE0003": "a measure whose findings are every record it counted, with no repair",
    "RS-OWNE0001": "a count whose repair is a choice between three different edits",
    "RS-OWNE0002": "a measure read beside its counterpart rather than on its own",
    "TS-MODU0001": "a count over the specifiers a module names rather than over a number",
    "TS-MODU0002": "a measure stating one finding for the record that produced the maximum",
    "TS-TYPE0001": "a count over records a frontend had to learn to look through an export for",
    "TS-TYPE0002": "a percentage whose findings are the occurrences behind the share",
}


def exemplars() -> dict[str, str]:
    """Return the worked rule shapes this contract suite covers."""
    return _EXEMPLARS


def fixture() -> dict[str, str]:
    """Return the repository sources that provoke every migrated finding."""
    return _FIXTURE


def wide_families() -> set[str]:
    """Return fact families whose one row describes the whole repository."""
    return _WIDE
