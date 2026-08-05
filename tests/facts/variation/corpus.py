_FIXTURE: dict[str, str] = {
    "pyproject.toml": (
        """[project]
name = "shop"
requires-python = ">=3.12"

[tool.pytest.ini_options]
addopts = "-q --strict-config"
import_mode = "append"
anyio_mode = "strict"

[tool.ruff]
target-version = "py312"

[tool.ruff.per-file-target-version]
"shop/legacy.py" = "py311"
"""
    ),
    "chefe.toml": (
        """[tasks]
setup = "sudo apt-get install -y libshop"
lint = "ruff check ."
typecheck = "mypy src"
test = "python -m pytest"
build = "python -m build --outdir .dist"
shell = "docker run -it shop bash"

[envs.ci.tasks]
test = "python -m pytest -x"
"""
    ),
    "shop/__init__.py": (
        'from .service import Ledger, render\n\n__all__ = ["Ledger", "render"]\n'
    ),
    "client.py": "from shop import Ledger\n\nledger = Ledger([])\n",
    "external.py": "from shop.service import Ledger\n\nledger = Ledger([])\n",
    "external_grouped.py": (
        "from shop.service import Ledger, render\n\nledger = Ledger([])\ntext = render(ledger)\n"
    ),
    "warehouse/__init__.py": ('from .models import Stock\n\n__all__ = ["Stock"]\n'),
    "warehouse/models.py": "class Stock:\n    pass\n",
    "warehouse_user.py": "from warehouse.models import Stock\n\nstock = Stock()\n",
    "facade/__init__.py": (
        'from consumer import use\nfrom engine import Engine\n\n__all__ = ["Engine"]\n'
    ),
    "engine.py": "class Engine:\n    pass\n",
    "consumer.py": "from engine import Engine\n\nuse = Engine\n",
    "shop/models.py": (
        """from dataclasses import dataclass
from typing import final

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


@final
class FrozenFlexModel:
    pass


@final
class ExtensionBoundary(FrozenFlexModel):
    adapter: str


@dataclass
class LegacyPoint:
    x: int


class Credential(BaseModel):
    model_config = ConfigDict(frozen=True)

    labels: tuple[str, ...] = ()
    token: str | None = None
    username: str | None = None
    certificate: bytes | None = None

    @field_validator('token')
    @classmethod
    def normalized(cls, value: str) -> str:
        if len(value) < 2:
            raise ValueError('short')
        return value.strip()

    @model_validator(mode='after')
    def one_variant(self):
        variants = (self.token, self.username, self.certificate)
        if sum(value is not None for value in variants) > 1:
            raise ValueError('choose one')
        return self

    @model_validator(mode='after')
    def prepared(self):
        self.prepare()
        return self

    @model_validator(mode='before')
    @classmethod
    def unchanged(cls, value):
        return value


class SavedCredential(Credential):
    pass
"""
    ),
    "shop/errors.py": (
        '''class OrderError(Exception):
    """One order could not be placed."""


class OrderLineError(OrderError):
    """One line of an order could not be placed."""
'''
    ),
    # A drawn separator is what fixed repetition evidence exists to find, and house style forbids
    # one, so the only place this repository can hold the shape is a project it writes on purpose.
    "shop/banner.py": (
        '''def rule_off() -> str:
    """Return the line a report draws under its heading."""
    return "===="
'''
    ),
    "shop/constants.py": "_DEFAULT_TIMEOUT = 5\n",
    "shop/support.py": (
        """class ServiceSupport:
    def __init__(self) -> None:
        self.ready = True

    def normalize(self, value: str, strip: bool = True) -> str:
        return value.strip() if strip else value
"""
    ),
    "shop/concrete.py": (
        """from .support import ServiceSupport


class Service(ServiceSupport):
    def __init__(self) -> None:
        super().__init__()

    def normalize(self, value: str, strip: bool = True) -> str:
        return super().normalize(value, strip)
"""
    ),
    "shop/service.py": (
        '''from .errors import OrderError

FORMATS = ("json", "toml")


class Ledger:
    """Hold what one shop recorded."""

    def __init__(self, rows: list[str]) -> None:
        self.rows = rows

    @property
    def size(self) -> int:
        """How many rows the ledger holds."""
        return len(self.rows)

    def __len__(self) -> int:
        return self.size

    def widest(self) -> int:
        """Return the longest row, reached through the name this class states."""
        return Ledger.longest(self.rows)

    @staticmethod
    def longest(rows: list[str]) -> int:
        """Return how long the longest of these rows is."""
        return max((len(row) for row in rows), default=0)


def render(kind: str, value: str) -> str:
    """Render one value the way its kind asks for."""
    if kind == "json":
        return value
    elif kind == "toml":
        head = value.strip()
        return head
    elif kind == "yaml":
        return value.upper()
    else:
        return ""


def widen(names: list[str]) -> list[str]:
    """Widen every name, reading the suffixes only by iterating them."""
    suffixes = ["json", "toml"]
    return [f"{name}.{suffix}" for name in names for suffix in suffixes]


def known(name: str) -> bool:
    """Whether one name is one this shop writes, read only as a membership test."""
    allowed = ["json", "toml"]
    return name in allowed


def leading(rows: list[str]) -> str:
    """Return the first row, which indexes the literal and settles nothing."""
    order = ["json", "toml"]
    return order[0] + rows[0]


def place(kind: str) -> None:
    """Place one order, or say why it could not be placed."""
    if kind not in FORMATS:
        raise OrderError(kind)


def encode(kind: str) -> str:
    """Pass a mapping through a nested call expression."""
    return render("json", str(dict({"format": kind})))


@rule("SHOP-TEST0001")
def query(subject):
    """Describe one declarative table plan."""
    return subject.lazy("orders")
'''
    ),
    "shop/api.py": (
        '''from .constants import _DEFAULT_TIMEOUT
from .enums.payment import PaymentState
from .errors import OrderError
from .service import place


def submit(kind: str) -> str:
    """Submit one order and name what came back."""
    try:
        place(kind)
        result = "placed"
    except OrderError:
        return "rejected"
    return result
'''
    ),
    "shop/jobs.py": (
        '''from .enums.payment import PaymentState
from .errors import OrderError
from .service import place


def sweep(kinds: list[str]) -> int:
    """Place every order it can and count the ones it could not."""
    refused = 0
    # placed = [place(kind) for kind in kinds]
    for kind in kinds:  # noqa: PERF203
        try:
            place(kind)
        except OrderError:
            refused += 1
    return refused
'''
    ),
    "tests/test_checkout.py": (
        """import pytest


@pytest.mark.flaky(
    age_days=30,
    owner='checkout',
    remediation='https://example.com/issues/checkout',
    recurred_after_repair=True,
)
def test_retried_checkout() -> None:
    pass


@pytest.mark.quarantine
def test_unowned_checkout() -> None:
    pass
"""
    ),
    "shop/status.py": (
        '''from enum import IntEnum, StrEnum, auto


class Stage(StrEnum):
    """Name where one order sits."""

    PLACED = auto()
    SHIPPED = auto()


class Priority(IntEnum):
    """Name how urgently one order ships."""

    LOW = 1
    HIGH = 2


STAGE_LABELS = {Stage.PLACED: "Placed", "other": "Other"}


PRIORITY_LABELS = {Priority.LOW: "Low", Priority.HIGH: "High"}


def waiting(stage: str) -> bool:
    """Whether one stage is still waiting on somebody."""
    if stage == Stage.PLACED:
        return True
    elif stage == Stage.SHIPPED:
        return False
    return False
'''
    ),
    "shop/enums/__init__.py": "",
    "shop/enums/payment.py": (
        '''from enum import StrEnum, auto


class PaymentState(StrEnum):
    """Name where payment processing sits."""

    PENDING = auto()
    SETTLED = auto()
'''
    ),
    "shop/database.py": (
        """from sqlmodel import Field, SQLModel, Session, select


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)


def load(session: Session, order_id: int) -> Order | None:
    for _ in range(1):
        session.commit()
    session.exec(
        select(Order).where(Order.id == order_id)
        .execution_options(populate_existing=True)
    ).first()
    return session.exec(select(Order).where(Order.id == order_id)).first()
"""
    ),
    "shop/lookup.py": (
        '''def label(wanted: str) -> str:
    """Read one label out of a table nothing but the lookup reads."""
    rows = [("open", "Open"), ("closed", "Closed")]
    for key, value in rows:
        if key == wanted:
            return value
    return ""


def widths(wanted: str) -> int:
    """Read a table the body also measures, which no mapping states more clearly."""
    rows = [("open", 4), ("open", 6), ("closed", 6)]
    total = len(rows)
    for key, value in rows:
        if key == wanted:
            return value
    return total


def totals(wanted: str) -> int:
    """Rebind one table, which is what stops a mapping from stating it."""
    rows = [("open", 1), ("closed", 2)]
    rows = [*rows, ("held", 3)]
    for key, value in rows:
        if key == wanted:
            return value
    return 0


class Receipt:
    """Hold what one order was charged, and refuse a charge nobody can pay."""

    def __init__(self, order: str, amount: int = 0, currency: str = "JPY") -> None:
        if amount < 0:
            raise ValueError(order)
        self.order = order
        self.amount = amount
        self.currency = currency

    def __repr__(self) -> str:
        return f"{self.order}:{self.amount}"
'''
    ),
    "shop/test_shop.py": (
        '''from typing import Annotated

import pytest
from pydantic import Field

from .lookup import label
from .service import render

SEEN: list[str] = []


def charge(amount: Annotated[int, Field(description="what one line cost")]) -> int:
    """Take a price whose metadata describes this field and nothing else."""
    return amount


def helper(value: str) -> str:
    """Not a test, and the test below it is not one either."""

    def test_inner() -> None:
        assert value

    return value


def test_labels_are_read_from_the_table() -> None:
    """A collected test that walks its own cases and checks each one."""
    for key in ["open", "closed"]:
        assert label(key)


def test_renders_every_kind() -> None:
    """A collected test that writes to state the module holds."""
    SEEN.append(render("j","a"))  # noqa: PERF401 reason=x since=2020-01-02 expires=2099-01-01
    assert SEEN


@pytest.mark.parametrize("value", range(3))
def test_range_case(value: int) -> None:
    """Retain the cardinality of one generated parameter range."""
    assert value >= 0
'''
    ),
    "src/lifetimes.rs": (
        """pub fn describe(name: &'static str) -> usize {
    name.len()
}

pub fn spawn<T: Send + 'static>(value: T) {
    drop(value);
}
"""
    ),
}

_MANIFESTLESS: dict[str, str] = {
    "src/engine.cuh": (
        """#pragma once

// TODO: hand the merge its own stream
struct Engine {
  int limit;
};

__global__ void scale(float* data, int count);
"""
    ),
    "src/engine.cu": (
        """#include "engine.cuh"

__global__ void scale(float* data, int count) {
  int index = 0;
  if (index < count) {
    data[index] = data[index] * 2.0f;
  }
}

void run(float* data, int count) {
  scale<<<count, 256>>>(data, count);
}
"""
    ),
}


def fixture_files() -> dict[str, str]:
    """Return the repository corpus that exercises provider variation."""
    return dict(_FIXTURE)


def manifestless_files() -> dict[str, str]:
    """Return the corpus that exercises repositories without manifests."""
    return dict(_MANIFESTLESS)
