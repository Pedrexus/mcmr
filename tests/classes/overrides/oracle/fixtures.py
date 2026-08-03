_SIGNATURES = '''class Base:
    def fewer(self, first, second):
        """Base."""

    def more(self, first):
        """Base."""

    def more_optional(self, first):
        """Base."""

    def renamed(self, first):
        """Base."""

    def reordered(self, first, second):
        """Base."""

    def defaulted(self, first=1):
        """Base."""

    def required(self, first):
        """Base."""

    def swallowed(self, first, second):
        """Base."""

    def star_kept(self, first, *rest):
        """Base."""

    def star_lost(self, first, *rest):
        """Base."""

    def kwargs_lost(self, first, **rest):
        """Base."""

    def kwonly_added(self, first, *, flag):
        """Base."""

    def kwonly_optional(self, first, *, flag):
        """Base."""

    def kwonly_gone(self, first, *, flag):
        """Base."""

    def kwonly_renamed(self, first, *, flag):
        """Base."""

    def kwargs_absorb(self, first, *, flag):
        """Base."""

    def mixed(self, first, second, *, flag):
        """Base."""

    def placeholder(self, _unused):
        """Base."""

    def kwonly_default(self, *, flag=1):
        """Base."""

    @staticmethod
    def unbound(first, second):
        """Base."""

    @classmethod
    def classy(cls, first):
        """Base."""

    def __private(self, first, second):
        """Base."""

    def __eq__(self, other):
        """Base."""


class Narrowed(Base):
    def fewer(self, first):
        """Child."""


class Widened(Base):
    def more(self, first, second):
        """Child."""


class WidenedOptional(Base):
    def more_optional(self, first, second=2):
        """Child."""


class Renamer(Base):
    def renamed(self, other):
        """Child."""


class Reorderer(Base):
    def reordered(self, second, first):
        """Child."""


class Requirer(Base):
    def defaulted(self, first):
        """Child."""


class Relaxer(Base):
    def required(self, first=1):
        """Child."""


class Swallower(Base):
    def swallowed(self, *args):
        """Child."""


class StarKeeper(Base):
    def star_kept(self, first, *rest):
        """Child."""


class StarLost(Base):
    def star_lost(self, first):
        """Child."""


class KwargsLost(Base):
    def kwargs_lost(self, first):
        """Child."""


class KwonlyAdder(Base):
    def kwonly_added(self, first, *, flag, extra):
        """Child."""


class KwonlyOptional(Base):
    def kwonly_optional(self, first, *, flag, extra=1):
        """Child."""


class KwonlyGone(Base):
    def kwonly_gone(self, first):
        """Child."""


class KwonlyRenamer(Base):
    def kwonly_renamed(self, first, *, other):
        """Child."""


class KwargsAbsorber(Base):
    def kwargs_absorb(self, first, **rest):
        """Child."""


class MixedChange(Base):
    def mixed(self, one, two, *, extra):
        """Child."""


class Placeholder(Base):
    def placeholder(self, value):
        """Child."""


class KwonlyDefaultLost(Base):
    def kwonly_default(self, *, flag):
        """Child."""


class StaticRenamer(Base):
    @staticmethod
    def unbound(other, second):
        """Child."""


class ClassRenamer(Base):
    @classmethod
    def classy(klass, first):
        """Child."""


class PrivateChange(Base):
    def __private(self, first):
        """Child."""


class DunderChange(Base):
    def __eq__(self, other, extra):
        """Child."""


class Middle(Base):
    def fewer(self, first, second):
        """Middle."""


class Leaf(Middle):
    def fewer(self, first, second, third):
        """Leaf."""
'''

_POSITIONS = '''class Slots:
    def kept(self, first, second, /):
        """Base."""

    def dropped(self, first, second, /):
        """Base."""

    def renamed(self, first, /, second):
        """Base."""

    def defaulted(self, first=1, /):
        """Base."""


class SlotKeeper(Slots):
    def kept(self, first, second, /):
        """Child."""


class SlotDropper(Slots):
    def dropped(self, first, /):
        """Child."""


class SlotRenamer(Slots):
    def renamed(self, other, /, second):
        """Child."""


class SlotRequirer(Slots):
    def defaulted(self, first, /):
        """Child."""
'''

_PROTOCOLS = """from typing import final


class Base:
    def __init__(self):
        self.hidden = None

    @property
    def size(self):
        return 1

    async def fetch(self):
        return 2

    def plain(self):
        return 3

    @final
    def sealed(self):
        return 4


class Deviant(Base):
    def __init__(self):
        super().__init__()

    def size(self):
        return 5

    def fetch(self):
        return 6

    async def plain(self):
        return 7

    def sealed(self):
        return 8

    def hidden(self):
        return 9
"""

_INITIALIZERS = """class Connection:
    def __init__(self):
        self.socket = 1


class Session:
    def __init__(self):
        self.token = 2


class Pooled(Connection):
    def __init__(self):
        self.pool = []


class Polite(Connection):
    def __init__(self):
        super().__init__()


class Borrower(Connection):
    def __init__(self):
        Session.__init__(self)
"""

_PROMISES = '''from abc import ABC, abstractmethod


class Contract(ABC):
    @abstractmethod
    def encode(self, value):
        """Encode."""


class Guarded(Contract):
    def describe(self):
        return "guarded"


class Promise:
    @abstractmethod
    def decode(self, value):
        """Decode."""


class Concrete(Promise):
    def describe(self):
        return "concrete"
'''

_SEALED = """from typing import final


@final
class Money:
    def __init__(self, cents):
        self.cents = cents


class Discount(Money):
    def apply(self, rate):
        return self.cents * rate
"""


def signatures() -> str:
    """Return signature override cases shared by the Pylint oracle."""
    return _SIGNATURES


def positions() -> str:
    """Return positional-only override cases."""
    return _POSITIONS


def protocols() -> str:
    """Return call-protocol override cases."""
    return _PROTOCOLS


def initializers() -> str:
    """Return initializer-chain cases."""
    return _INITIALIZERS


def promises() -> str:
    """Return abstract promise cases."""
    return _PROMISES


def sealed() -> str:
    """Return final class and member cases."""
    return _SEALED
