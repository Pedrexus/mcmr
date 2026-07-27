import json
import subprocess
from pathlib import Path

import pytest

from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.facts import (
    MemberDeclaration,
    OverrideFact,
    ParameterDeclaration,
    ParameterKind,
    SourceSpan,
)
from mcmr.kernel import Kernel, locate
from mcmr.rules.general.deterministic.overrides.r0001 import (
    overriding_method_accepts_different_arguments,
)
from mcmr.rules.general.deterministic.overrides.r0002 import overriding_method_renames_a_parameter
from mcmr.rules.general.deterministic.overrides.r0003 import (
    overriding_method_demands_an_argument_the_base_defaulted,
)
from mcmr.rules.general.deterministic.overrides.r0004 import (
    overriding_method_changes_its_call_protocol,
)
from mcmr.rules.general.deterministic.overrides.r0005 import abstract_member_left_unimplemented
from mcmr.rules.general.deterministic.overrides.r0006 import subclass_initializer_skips_its_base
from mcmr.rules.general.deterministic.overrides.r0007 import initializer_called_on_a_stranger
from mcmr.rules.general.deterministic.overrides.r0008 import final_method_overridden
from mcmr.rules.general.deterministic.overrides.r0009 import final_class_subclassed
from mcmr.rules.general.deterministic.overrides.r0010 import inherited_attribute_hides_a_method
from mcmr.upstream import ClaimIndex, Coverage, ToolCoverage

ROOT = Path(__file__).parents[1]

needs_kernel = pytest.mark.skipif(
    not locate(ROOT).exists(),
    reason="the differential oracle needs the kernel binary this checkout builds",
)


def member(
    name: str,
    *parameters: str,
    decorators: tuple[str, ...] = (),
    asynchronous: bool = False,
    data: bool = False,
) -> MemberDeclaration:
    """Build one member exactly as the class holding it would write it down.

    Each parameter is spelled the way Python spells it, so `path`, `path=1`, `*rest`, `**extra`,
    and the bare `/` and `*` separators mean here what they mean in a real signature.
    """
    return MemberDeclaration(
        name=name,
        parameters=None if data else spelled(parameters),
        decorators=list(decorators),
        asynchronous=asynchronous,
    )


def spelled(parameters: tuple[str, ...]) -> list[ParameterDeclaration]:
    """Read one signature spelled the way Python spells it into the parameters it states."""
    kind = ParameterKind.POSITIONAL_OR_KEYWORD
    stated: list[ParameterDeclaration] = []
    for item in parameters:
        if item == "/":
            stated = [
                held.model_copy(update={"kind": ParameterKind.POSITIONAL_ONLY}) for held in stated
            ]
        elif item == "*":
            kind = ParameterKind.KEYWORD_ONLY
        elif item.startswith("**"):
            stated.append(
                ParameterDeclaration(name=item.removeprefix("**"), kind=ParameterKind.VAR_KEYWORD)
            )
        elif item.startswith("*"):
            stated.append(
                ParameterDeclaration(
                    name=item.removeprefix("*"), kind=ParameterKind.VAR_POSITIONAL
                )
            )
            kind = ParameterKind.KEYWORD_ONLY
        else:
            named, _, default = item.partition("=")
            stated.append(ParameterDeclaration(name=named, kind=kind, has_default=bool(default)))
    return stated


def link(
    *,
    depth: int = 1,
    base: str = "pkg.Base",
    base_decorators: tuple[str, ...] = (),
    base_names: tuple[str, ...] = ("Base",),
    ancestor_names: tuple[str, ...] = ("Base",),
    declared: tuple[MemberDeclaration, ...] = (),
    inherited: tuple[MemberDeclaration, ...] = (),
    initializer_calls: tuple[str, ...] = (),
) -> OverrideFact:
    """Build one inheritance link in the shape the analysis kernel states it."""
    return OverrideFact(
        key=f"override:pkg.Child:{base}",
        span=SourceSpan(path="pkg/example.py"),
        derived="pkg.Child",
        base=base,
        depth=depth,
        base_decorators=list(base_decorators),
        base_names=list(base_names),
        ancestor_names=list(ancestor_names),
        declared=list(declared),
        inherited=list(inherited),
        initializer_calls=list(initializer_calls),
    )


def pylint_findings(root: Path, symbol: str) -> dict[str, int]:
    """Return how many times Pylint reports one message, keyed by the class it names."""
    completed = subprocess.run(
        [
            "python",
            "-m",
            "pylint",
            "--disable=all",
            f"--enable={symbol}",
            "--output-format=json2",
            "--score=n",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(completed.stdout or '{"messages": []}')
    found: dict[str, int] = {}
    for item in report["messages"]:
        named = str(item["obj"]).split(".")[0]
        found[named] = found.get(named, 0) + 1
    return found


def mcmr_findings(root: Path, rule_id: str) -> dict[str, int]:
    """Return what one MCMR rule reports over the same tree, keyed by the subclass it names."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    definition = next(item for item in catalog.definitions if item.id == rule_id)
    rule = next(item for item in catalog.rules if item.callable_path == definition.callable)
    workspace = Kernel(binary=locate(ROOT), root=root).build(
        [OverrideFact.__name__], {OverrideFact.__name__: OverrideFact}
    )
    found: dict[str, int] = {}
    for fact in workspace.stream(OverrideFact):
        outcome = rule.invoke(fact, settings={}, dependencies={})
        value = outcome if isinstance(outcome, int) else 0
        if value:
            named = fact.derived.rsplit(".", 1)[-1]
            found[named] = found.get(named, 0) + value
    return found


def written(root: Path, name: str, source: str) -> Path:
    """Write one generated module and return the directory holding it."""
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(source)
    return root


SIGNATURES = '''class Base:
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

POSITIONS = '''class Slots:
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

PROTOCOLS = """from typing import final


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

INITIALIZERS = """class Connection:
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

PROMISES = '''from abc import ABC, abstractmethod


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

SEALED = """from typing import final


@final
class Money:
    def __init__(self, cents):
        self.cents = cents


class Discount(Money):
    def apply(self, rate):
        return self.cents * rate
"""


def test_an_override_that_stops_accepting_what_the_base_accepts_is_reported() -> None:
    """A caller holding the base passes an argument the override can no longer take."""
    narrowed = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "encoding"),),
    )
    widened = link(
        declared=(member("load", "self", "path", "encoding"),),
        inherited=(member("load", "self", "path"),),
    )
    extended = link(
        declared=(member("load", "self", "path", "encoding=None"),),
        inherited=(member("load", "self", "path"),),
    )
    variadic = link(
        declared=(member("load", "self", "*args"),),
        inherited=(member("load", "self", "path", "encoding"),),
    )
    tail_lost = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "*rest"),),
    )
    mapping_lost = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "**rest"),),
    )
    counted_and_lost = link(
        declared=(member("load", "self"),),
        inherited=(member("load", "self", "path", "*rest"),),
    )

    assert overriding_method_accepts_different_arguments(narrowed) == 1
    assert overriding_method_accepts_different_arguments(widened) == 1
    assert overriding_method_accepts_different_arguments(extended) == 0
    assert overriding_method_accepts_different_arguments(variadic) == 0
    assert overriding_method_accepts_different_arguments(tail_lost) == 1
    assert overriding_method_accepts_different_arguments(mapping_lost) == 1
    assert overriding_method_accepts_different_arguments(counted_and_lost) == 2


def test_a_keyword_only_parameter_is_reached_by_its_name_and_by_nothing_else() -> None:
    """Adding, dropping, or renaming one deletes an argument rather than moving it."""
    added = link(
        declared=(member("load", "self", "path", "*", "mode"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    optional = link(
        declared=(member("load", "self", "path", "*", "flag", "mode=None"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    dropped = link(
        declared=(member("load", "self", "path"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    absorbed = link(
        declared=(member("load", "self", "path", "**rest"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )
    kept = link(
        declared=(member("load", "self", "path", "*", "flag"),),
        inherited=(member("load", "self", "path", "*", "flag"),),
    )

    assert overriding_method_accepts_different_arguments(added) == 1
    assert overriding_method_accepts_different_arguments(optional) == 0
    assert overriding_method_accepts_different_arguments(dropped) == 1
    assert overriding_method_accepts_different_arguments(absorbed) == 0
    assert overriding_method_accepts_different_arguments(kept) == 0
    assert overriding_method_renames_a_parameter(added) == 0


def test_a_position_no_caller_can_name_counts_as_an_argument_and_never_as_a_name() -> None:
    """A slot dropped breaks every caller, and a slot renamed breaks nobody who could name it."""
    dropped = link(
        declared=(member("load", "self", "path", "/"),),
        inherited=(member("load", "self", "path", "encoding", "/"),),
    )
    renamed = link(
        declared=(member("load", "self", "target", "/", "encoding"),),
        inherited=(member("load", "self", "path", "/", "encoding"),),
    )
    absorbed = link(
        declared=(member("load", "self", "path", "/", "*rest"),),
        inherited=(member("load", "self", "path", "encoding", "/"),),
    )

    assert overriding_method_accepts_different_arguments(dropped) == 1
    assert overriding_method_accepts_different_arguments(renamed) == 0
    assert overriding_method_renames_a_parameter(renamed) == 0
    assert overriding_method_accepts_different_arguments(absorbed) == 0


def test_a_name_python_owns_or_rewrites_is_outside_the_substitution_contract() -> None:
    """No caller can substitute through a mangled name and the interpreter calls the rest."""
    mangled = link(
        declared=(member("__helper", "self"),),
        inherited=(member("__helper", "self", "value"),),
    )
    inherited_data = link(
        declared=(member("run", "self"),),
        inherited=(member("run", data=True),),
    )
    declared_data = link(
        declared=(member("run", data=True),),
        inherited=(member("run", "self", "value"),),
    )
    setter = link(
        declared=(member("size", "self", "value", decorators=("size.setter",)),),
        inherited=(member("size", "self"),),
    )

    assert overriding_method_accepts_different_arguments(mangled) == 0
    assert overriding_method_accepts_different_arguments(inherited_data) == 0
    assert overriding_method_accepts_different_arguments(declared_data) == 0
    assert overriding_method_accepts_different_arguments(setter) == 0


def test_an_override_that_changes_a_parameter_name_is_reported() -> None:
    """Every ordinary parameter is also a keyword, so a rename deletes part of the interface."""
    renamed = link(
        declared=(member("save", "self", "entry"),),
        inherited=(member("save", "self", "record"),),
    )
    reordered = link(
        declared=(member("send", "self", "timeout", "payload"),),
        inherited=(member("send", "self", "payload", "timeout"),),
    )
    placeholder = link(
        declared=(member("save", "self", "record"),),
        inherited=(member("save", "self", "_unused"),),
    )
    counted = link(
        declared=(member("save", "self", "entry"),),
        inherited=(member("save", "self", "record", "stamp"),),
    )
    receiver = link(
        declared=(member("build", "klass", "value", decorators=("classmethod",)),),
        inherited=(member("build", "cls", "value", decorators=("classmethod",)),),
    )
    kept = link(
        declared=(member("save", "self", "record"),),
        inherited=(member("save", "self", "record"),),
    )

    assert overriding_method_renames_a_parameter(renamed) == 1
    assert overriding_method_renames_a_parameter(reordered) == 2
    assert overriding_method_renames_a_parameter(placeholder) == 0
    assert overriding_method_renames_a_parameter(counted) == 0
    assert overriding_method_renames_a_parameter(receiver) == 0
    assert overriding_method_renames_a_parameter(kept) == 0
    assert overriding_method_renames_a_parameter(link()) == 0


def test_an_override_that_withdraws_a_default_the_base_offered_is_reported() -> None:
    """Every call keeps its shape and only the calls that relied on the default break."""
    withdrawn = link(
        declared=(member("send", "self", "timeout"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    relaxed = link(
        declared=(member("send", "self", "timeout=30"),),
        inherited=(member("send", "self", "timeout"),),
    )
    swallowed = link(
        declared=(member("send", "self", "timeout", "*rest"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    renamed = link(
        declared=(member("send", "self", "delay"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    counted = link(
        declared=(member("send", "self"),),
        inherited=(member("send", "self", "timeout=30"),),
    )
    keyword = link(
        declared=(member("send", "self", "*", "flag"),),
        inherited=(member("send", "self", "*", "flag=True"),),
    )

    assert overriding_method_demands_an_argument_the_base_defaulted(withdrawn) == 1
    assert overriding_method_demands_an_argument_the_base_defaulted(relaxed) == 0
    assert overriding_method_demands_an_argument_the_base_defaulted(swallowed) == 0
    assert overriding_method_demands_an_argument_the_base_defaulted(renamed) == 0
    assert overriding_method_demands_an_argument_the_base_defaulted(counted) == 0
    assert overriding_method_demands_an_argument_the_base_defaulted(keyword) == 0
    assert overriding_method_demands_an_argument_the_base_defaulted(link()) == 0


def test_an_override_that_changes_how_a_caller_reaches_it_is_reported() -> None:
    """A property read as a method and a coroutine nobody awaits both fail far away."""
    unwrapped = link(
        declared=(member("size", "self"),),
        inherited=(member("size", "self", decorators=("property",)),),
    )
    awaited = link(
        declared=(member("read", "self", asynchronous=True),),
        inherited=(member("read", "self"),),
    )
    setter = link(
        declared=(member("size", "self", "value", decorators=("size.setter",)),),
        inherited=(member("size", "self", decorators=("functools.cached_property",)),),
    )
    steady = link(
        declared=(member("read", "self"),),
        inherited=(member("read", "self"),),
    )

    assert overriding_method_changes_its_call_protocol(unwrapped) == 1
    assert overriding_method_changes_its_call_protocol(awaited) == 1
    assert overriding_method_changes_its_call_protocol(setter) == 0
    assert overriding_method_changes_its_call_protocol(steady) == 0


def test_a_promise_a_concrete_subclass_never_kept_is_reported() -> None:
    """A concrete class holding an open contract raises for whoever instantiates it."""
    open_promise = link(
        declared=(member("describe", "self"),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )
    under_abc = link(
        ancestor_names=("Base", "ABC"),
        declared=(member("describe", "self"),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )
    still_abstract = link(
        declared=(member("decode", "self", "value", decorators=("abc.abstractmethod",)),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )
    kept = link(
        declared=(member("encode", "self", "value"),),
        inherited=(member("encode", "self", "value", decorators=("abstractmethod",)),),
    )

    assert abstract_member_left_unimplemented(open_promise) == 1
    assert (
        abstract_member_left_unimplemented(open_promise, abstract_bases=frozenset({"Base"})) == 0
    )
    assert abstract_member_left_unimplemented(under_abc) == 0
    assert abstract_member_left_unimplemented(still_abstract) == 0
    assert abstract_member_left_unimplemented(kept) == 0


def test_a_subclass_that_never_runs_the_initializer_above_it_is_reported() -> None:
    """Half a constructor ran, so the object exists with every base attribute missing."""
    skipped = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
    )
    polite = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
        initializer_calls=("super",),
    )
    direct = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
        initializer_calls=("Base",),
    )
    inherited_intact = link(inherited=(member("__init__", "self"),))
    promised = link(
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self", decorators=("abstractmethod",)),),
    )
    grandparent = link(
        depth=2,
        declared=(member("__init__", "self"),),
        inherited=(member("__init__", "self"),),
    )

    assert subclass_initializer_skips_its_base(skipped) == 1
    assert subclass_initializer_skips_its_base(polite) == 0
    assert subclass_initializer_skips_its_base(direct) == 0
    assert subclass_initializer_skips_its_base(inherited_intact) == 0
    assert subclass_initializer_skips_its_base(promised) == 0
    assert subclass_initializer_skips_its_base(grandparent) == 0


def test_an_initializer_run_on_a_class_nobody_inherits_is_reported() -> None:
    """Borrowing setup by hand binds two types together with a line nobody documented."""
    stranger = link(initializer_calls=("Session",))
    polite = link(initializer_calls=("super",))
    declared_base = link(initializer_calls=("Base",))
    second_link = link(
        base="pkg.Mixin", base_names=("Base", "Mixin"), initializer_calls=("Other",)
    )

    assert initializer_called_on_a_stranger(stranger) == 1
    assert initializer_called_on_a_stranger(polite) == 0
    assert initializer_called_on_a_stranger(declared_base) == 0
    assert initializer_called_on_a_stranger(second_link) == 0


def test_an_override_of_a_sealed_member_is_reported() -> None:
    """The base still assumes what the sealed member guaranteed and no longer gets it."""
    broken = link(
        declared=(member("balance", "self"),),
        inherited=(member("balance", "self", decorators=("typing.final",)),),
    )
    open_member = link(
        declared=(member("balance", "self"),),
        inherited=(member("balance", "self"),),
    )
    rebound = link(
        declared=(member("balance", data=True),),
        inherited=(member("balance", "self", decorators=("final",)),),
    )

    assert final_method_overridden(broken) == 1
    assert final_method_overridden(open_member) == 0
    assert final_method_overridden(rebound) == 0


def test_a_subclass_of_a_sealed_class_is_reported() -> None:
    """Sealing a class says its invariants were never meant to have a stranger inside."""
    assert final_class_subclassed(link(base_decorators=("final",))) is True
    assert final_class_subclassed(link(base_decorators=("typing.final",))) is True
    assert final_class_subclassed(link(base_decorators=("final",), depth=2)) is False
    assert final_class_subclassed(link()) is False


def test_a_method_an_ancestor_already_bound_to_data_is_reported() -> None:
    """Python resolves the instance attribute first, so the method below is never reached."""
    hidden = link(
        declared=(member("run", "self"),),
        inherited=(member("run", data=True),),
    )
    plain = link(
        declared=(member("run", "self"),),
        inherited=(member("run", "self"),),
    )
    mangled = link(
        declared=(member("__run", "self"),),
        inherited=(member("__run", data=True),),
    )

    assert inherited_attribute_hides_a_method(hidden) == 1
    assert inherited_attribute_hides_a_method(plain) == 0
    assert inherited_attribute_hides_a_method(mangled) == 0


@needs_kernel
def test_arguments_differ_names_every_class_pylint_names(tmp_path: Path) -> None:
    """Both readers report a changed count, a changed keyword, and a swallowing tail dropped.

    The fixture states each shape once, including the two that need the parameter kinds and the
    defaults the graph now records, so a narrowing, a widening, an added required keyword, a
    dropped keyword, a renamed keyword, and a lost variadic all land on the same classes here as
    they do in Pylint.
    """
    root = written(tmp_path, "generated.py", SIGNATURES)

    oracle = pylint_findings(root, "arguments-differ")
    ours = mcmr_findings(root, "ALL-OVER0001")

    assert oracle == {
        "Narrowed": 1,
        "Widened": 1,
        "StarLost": 1,
        "KwargsLost": 1,
        "KwonlyAdder": 1,
        "KwonlyGone": 1,
        "KwonlyRenamer": 1,
        "MixedChange": 1,
        "Leaf": 1,
    }
    assert ours == oracle


@needs_kernel
def test_arguments_renamed_counts_the_same_moved_positions_pylint_counts(tmp_path: Path) -> None:
    """One message per position that changed name, which makes a transposition two of them.

    MCMR used to separate the rename from the reordering and only matched Pylint as a union of two
    rules. Counting positions rather than overrides is what closes it, and a reordering is now
    what it always was, which is two names that swapped places.
    """
    root = written(tmp_path, "generated.py", SIGNATURES)

    oracle = pylint_findings(root, "arguments-renamed")
    ours = mcmr_findings(root, "ALL-OVER0002")

    assert oracle == {"Renamer": 1, "Reorderer": 2, "MixedChange": 2, "StaticRenamer": 1}
    assert ours == oracle


@needs_kernel
def test_signature_differs_names_the_override_that_withdrew_a_default(tmp_path: Path) -> None:
    """The two readings met once the graph started recording which parameters carry a default.

    This rule used to answer a question of its own, a transposition, and was disjoint from Pylint
    by construction. It now answers what Pylint answers, which is an optional argument the
    override made required while changing nothing else.
    """
    root = written(tmp_path, "generated.py", SIGNATURES)

    oracle = pylint_findings(root, "signature-differs")
    ours = mcmr_findings(root, "ALL-OVER0003")

    assert oracle == {"Requirer": 1}
    assert ours == oracle


@needs_kernel
def test_a_dropped_positional_only_argument_is_reported_here_and_not_by_pylint(
    tmp_path: Path,
) -> None:
    """The one place these two readers part, and it is a gap in the oracle rather than in MCMR.

    Pylint reaches its positional comparison through the list of ordinary parameters its own
    parser builds, and a positional-only parameter is kept in a separate list that the comparison
    never opens. An override that drops one therefore breaks every caller in silence there. MCMR
    counts the slot, which is what a caller has to fill, and leaves the name alone, which is what
    no caller can pass, so the renaming and the withdrawn default still agree exactly.
    """
    root = written(tmp_path, "generated.py", POSITIONS)

    assert pylint_findings(root, "arguments-differ") == {}
    assert mcmr_findings(root, "ALL-OVER0001") == {"SlotDropper": 1}
    assert mcmr_findings(root, "ALL-OVER0002") == pylint_findings(root, "arguments-renamed") == {}
    assert (
        mcmr_findings(root, "ALL-OVER0003")
        == pylint_findings(root, "signature-differs")
        == {"SlotRequirer": 1}
    )


@needs_kernel
def test_a_changed_call_protocol_names_the_same_classes_pylint_names(tmp_path: Path) -> None:
    """Pylint splits the property half from the async half, so one method can cost two messages."""
    root = written(tmp_path, "generated.py", PROTOCOLS)

    oracle = pylint_findings(root, "invalid-overridden-method")
    ours = mcmr_findings(root, "ALL-OVER0004")

    assert oracle == {"Deviant": 3}
    assert ours == oracle


@needs_kernel
def test_a_sealed_member_and_a_sealed_class_agree_with_pylint(tmp_path: Path) -> None:
    """Both markers are read from the decorator, which is what Pylint reads too."""
    members = written(tmp_path / "members", "generated.py", PROTOCOLS)
    classes = written(tmp_path / "classes", "generated.py", SEALED)

    assert mcmr_findings(members, "ALL-OVER0008") == pylint_findings(
        members, "overridden-final-method"
    )
    assert mcmr_findings(members, "ALL-OVER0008") == {"Deviant": 1}
    assert mcmr_findings(classes, "ALL-OVER0009") == pylint_findings(
        classes, "subclassed-final-class"
    )
    assert mcmr_findings(classes, "ALL-OVER0009") == {"Discount": 1}


@needs_kernel
def test_a_hidden_method_agrees_with_pylint_where_the_hiding_is_inherited(tmp_path: Path) -> None:
    """The inherited half is the half an inheritance graph owns, and it matches exactly."""
    root = written(tmp_path, "generated.py", PROTOCOLS)

    oracle = pylint_findings(root, "method-hidden")
    ours = mcmr_findings(root, "ALL-OVER0010")

    assert oracle == {"Deviant": 1}
    assert ours == oracle


@needs_kernel
def test_both_initializer_messages_agree_with_pylint(tmp_path: Path) -> None:
    """A skipped base and a borrowed constructor are both read from resolved call edges."""
    root = written(tmp_path, "generated.py", INITIALIZERS)

    skipped = pylint_findings(root, "super-init-not-called")
    strangers = pylint_findings(root, "non-parent-init-called")

    assert skipped == {"Pooled": 1, "Borrower": 1}
    assert mcmr_findings(root, "ALL-OVER0006") == skipped
    assert strangers == {"Borrower": 1}
    assert mcmr_findings(root, "ALL-OVER0007") == strangers


@needs_kernel
def test_an_unkept_promise_agrees_with_pylint_including_what_it_declines_to_report(
    tmp_path: Path,
) -> None:
    """Pylint treats anything under `ABC` as abstract itself, and so does MCMR."""
    root = written(tmp_path, "generated.py", PROMISES)

    oracle = pylint_findings(root, "abstract-method")
    ours = mcmr_findings(root, "ALL-OVER0005")

    assert oracle == {"Concrete": 1}
    assert ours == oracle


@needs_kernel
def test_every_override_message_the_ledger_claims_has_a_case_behind_it() -> None:
    """A claim with no measurement behind it is an assertion, which is what the ledger is not.

    Counting the names written here proved only that ten names were written here. What the claim
    needs is that the ledger's own native Pylint messages for this family are exactly the ones a
    differential case above measures, so adding a claim without a case turns this red.
    """
    exercised = {
        "arguments-differ",
        "arguments-renamed",
        "signature-differs",
        "invalid-overridden-method",
        "abstract-method",
        "super-init-not-called",
        "non-parent-init-called",
        "overridden-final-method",
        "subclassed-final-class",
        "method-hidden",
    }
    definitions = tuple(Catalog(modules=RuleModuleDiscovery().modules).definitions)
    identifiers = {definition.id for definition in definitions}
    account = ToolCoverage(tool="pylint", claims=ClaimIndex(definitions=definitions))
    claimed = {
        entry.rule.symbol
        for entry in account.entries
        if entry.coverage is Coverage.NATIVE
        and any(named.startswith("ALL-OVER") for named in entry.rules)
    }

    assert {f"ALL-OVER{number:04d}" for number in range(1, 11)} <= identifiers
    assert claimed == exercised
