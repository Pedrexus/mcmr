import ast
import inspect
import re
import types
import typing
from enum import StrEnum
from functools import cache
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, TypeAliasType

import annotated_types
import pytest
from hypothesis import settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo

from mcmr.bases import FrozenFlexModel
from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.facts import Fact, SourceSpan, SyntaxFact, SyntaxNode
from mcmr.kernel import Kernel, locate
from mcmr.models import fact_type

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mcmr.models import Finding, RuleAnswer, RuleContract, RuleOutcome

ROOT = Path(__file__).parents[1]
BINARY = locate(ROOT)

needs_kernel = pytest.mark.skipif(not BINARY.exists(), reason="the analysis kernel is not built")

MATCHED = re.compile(r"^[A-Za-z_][A-Za-z0-9_.:/-]*$")

# The names no rule spells out but every rule reading a location or a receiver has to see.
NEUTRAL = ("", "src/orders.py", "tests/test_orders.py", "shop/api.py", "self", "total", "value")

settings.register_profile("mcmr", max_examples=25, deadline=None)
settings.load_profile("mcmr")


def synchronous(outcome: RuleOutcome) -> RuleAnswer:
    """Return the answer one synchronous rule produced, refusing an unstarted coroutine.

    A rule declares its outcome widely enough to cover the model lanes, so a test invoking a
    deterministic rule directly has to narrow that rather than assume it. Refusing the coroutine
    outright is what keeps a lane mistake from reading as a rule that answered nothing.
    """
    if inspect.isawaitable(outcome):
        raise TypeError("this rule answers asynchronously")
    return outcome


def measured(finding: Finding) -> dict[str, float]:
    """Return the named numbers one finding carries."""
    return {item.name: item.value for item in finding.measurements}


def written(root: Path, sources: dict[str, str]) -> Path:
    """Write one project out of a mapping of relative paths to source, and return its root."""
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


@cache
def built_catalog() -> Catalog:
    """Return the one built catalog every test reads its rules and definitions out of."""
    return Catalog(modules=RuleModuleDiscovery().modules)


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    """Return the built catalog, discovered once for the whole session."""
    return built_catalog()


def family_of(rule: RuleContract) -> type[Fact]:
    """Return the fact family one rule declares as its first parameter."""
    first = next(iter(rule.signature.parameters.values()))
    return fact_type(rule.hints[first.name])


def streams(root: Path, rules: Sequence[RuleContract]) -> dict[type[Fact], list[Fact]]:
    """Return every fact family the kernel builds over one repository for the given rules."""
    return dict(Kernel(binary=BINARY, root=root).run(rules).streams)


class Declaration(FrozenFlexModel):
    """Build the `SyntaxFact` a rule that reads code receives, without restating its frame.

    Five rule families ask for a declaration and each one used to spell the same six fields again.
    What actually varies between them is the file, the name, and the body, so those are what this
    takes and everything else is the frame a frontend always fills in the same way.
    """

    path: str
    qualname: str = "run"
    kind: str = "callable"
    language: str = "python"
    source: str = ""

    @property
    def span(self) -> SourceSpan:
        """Return the span every node of this declaration is located against."""
        return SourceSpan(path=self.path)

    def around(self, tree: SyntaxNode | None) -> SyntaxFact:
        """Return the fact carrying exactly this tree, which may be no tree at all."""
        return SyntaxFact(
            key=f"syntax:{self.path}:{self.qualname}",
            span=self.span,
            language=self.language,
            qualname=self.qualname,
            kind=self.kind,
            source=self.source,
            tree=tree,
        )

    def of(self, *body: SyntaxNode, span: SourceSpan | None = None) -> SyntaxFact:
        """Return the fact whose declaration node holds the given statements."""
        return self.around(
            SyntaxNode(
                kind=self.kind,
                name=self.qualname,
                text=self.source,
                span=span,
                children=list(body),
            )
        )


type FactValue = (
    bool
    | int
    | float
    | str
    | None
    | BaseModel
    | list[FactValue]
    | tuple[FactValue, ...]
    | dict[str, FactValue]
)

# What a test builder hands one model field. The containers are read-only so a caller can pass the
# `list[str]` or `dict[str, str]` it already has rather than restating it as a list of the union.
type Declared = (
    bool | int | float | str | None | BaseModel | Sequence[Declared] | Mapping[str, Declared]
)


class SchemaStrategy(FrozenFlexModel):
    """Derive a Hypothesis strategy for any fact from the model that declares it.

    A hand-written strategy is a second statement of the schema, and the two drift the moment a
    provider gains a field. Reading `model_fields` instead means a family that grows a field is
    explored the run after it is declared, and the domain each field states through
    `NonNegativeInt`, `PositiveInt`, or a bounded alias is the domain drawn from rather than a
    number a test happened to pick.

    Depth is bounded because several families nest records inside records. Past the bound the
    collections come back empty and the optional members come back absent, which terminates the
    one self-referential family without special-casing it.
    """

    depth: int = 2
    dialect: dict[str, tuple[str, ...]] = {"": NEUTRAL}

    def of[Model: BaseModel](self, model: type[Model], depth: int = 0) -> st.SearchStrategy[Model]:
        """Return the strategy building one validated instance of this model."""
        fields = {
            name: self.field(field.annotation, field.metadata, depth, name)
            for name, field in model.model_fields.items()
        }
        if not model.__pydantic_decorators__.model_validators:
            return st.builds(model, **fields)
        candidates = st.fixed_dictionaries(fields)
        valid = candidates.filter(lambda values: self.valid(model, values))
        return valid.map(model.model_validate)

    @staticmethod
    def valid[Model: BaseModel](model: type[Model], values: dict[str, FactValue]) -> bool:
        """Whether one generated field set satisfies the model's relational contracts."""
        try:
            model.model_validate(values)
        except ValidationError:
            return False
        return True

    def words(self, name: str) -> st.SearchStrategy[str]:
        """Return the words a rule decides on when it reads a field of this name.

        A rule opening with `if subject.kind != "callable"` is explored only by a fact whose kind
        is that word, and one word out of every string every rule mentions is a needle in a
        haystack. Reading which attribute each word was compared against turns the haystack into
        one small pile per field.

        The neutral names are drawn beside that pile rather than inside it, because the other half
        of what a rule decides on is two fields agreeing. A rule asking whether the first base is
        the base this link is about needs the two to coincide, and they never will while every
        string comes out of a pile of a hundred and fifty.
        """
        pool = self.dialect.get(name) or self.dialect[""]
        return st.sampled_from(NEUTRAL) | st.sampled_from(pool)

    def field(
        self,
        annotation: type | TypeAliasType | None,
        metadata: Sequence[FieldInfo | annotated_types.BaseMetadata],
        depth: int,
        name: str = "",
    ) -> st.SearchStrategy[FactValue]:
        """Return the strategy one declared field admits, following its own annotation."""
        if isinstance(annotation, TypeAliasType):
            return self.field(annotation.__value__, metadata, depth, name)
        origin, arguments = typing.get_origin(annotation), typing.get_args(annotation)
        if origin is typing.Annotated:
            return self.field(arguments[0], [*metadata, *arguments[1:]], depth, name)
        if origin in (types.UnionType, typing.Union):
            if depth >= self.depth and type(None) in arguments:
                return st.none()
            return st.one_of([self.field(item, metadata, depth, name) for item in arguments])
        if origin is list:
            if depth >= self.depth:
                return st.just([])
            return st.lists(self.field(arguments[0], (), depth + 1, name), max_size=3)
        if origin is tuple:
            if len(arguments) == 2 and arguments[1] is Ellipsis:
                return st.lists(self.field(arguments[0], (), depth + 1, name), max_size=3).map(
                    tuple
                )
            return st.tuples(*[self.field(item, (), depth + 1, name) for item in arguments])
        if origin is dict:
            # Every mapping a fact declares is keyed by a name, so the key takes the same
            # vocabulary the field does rather than a second reading of the annotation.
            if depth >= self.depth:
                return st.just({})
            return st.dictionaries(
                self.words(name), self.field(arguments[1], (), depth + 1, name), max_size=3
            )
        if origin is typing.Literal:
            return st.sampled_from(arguments)
        return self.scalar(annotation, self.interval(metadata), depth, name)

    def scalar(
        self,
        annotation: type | TypeAliasType | None,
        interval: dict[str, float],
        depth: int,
        name: str,
    ) -> st.SearchStrategy[FactValue]:
        """Return the strategy one leaf annotation admits, inside the interval it declares."""
        if annotation is type(None):
            return st.none()
        if annotation is bool:
            return st.booleans()
        if annotation is int:
            low, high = int(interval.get("minimum", -8)), int(interval.get("maximum", 40))
            near = [value for value in (0, 1, 2, 3) if low <= value <= high]
            spread = st.integers(min_value=low, max_value=high)
            return st.sampled_from(near) | spread if near else spread
        if annotation is float:
            return st.floats(
                min_value=interval.get("minimum", -8.0),
                max_value=interval.get("maximum", 120.0),
                allow_nan=False,
                allow_infinity=False,
            )
        if annotation is str:
            return self.words(name)
        if isinstance(annotation, type) and issubclass(annotation, StrEnum):
            return st.sampled_from(list(annotation))
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return self.of(annotation, depth + 1)
        raise TypeError(f"no strategy states the domain of {annotation!r}")

    @staticmethod
    def interval(
        metadata: Sequence[FieldInfo | annotated_types.BaseMetadata],
    ) -> dict[str, float]:
        """Read the closed interval one annotation declares, however pydantic spelled it."""
        found: dict[str, float] = {}
        for item in metadata:
            match item:
                case FieldInfo():
                    found |= SchemaStrategy.interval(item.metadata)
                case annotated_types.Ge(ge=int() | float() as bound):
                    found["minimum"] = bound
                case annotated_types.Gt(gt=int() | float() as bound):
                    found["minimum"] = bound + 1
                case annotated_types.Le(le=int() | float() as bound):
                    found["maximum"] = bound
                case annotated_types.Lt(lt=int() | float() as bound):
                    found["maximum"] = bound - 1
        return found


# Which reader method decides a value by reading which field, so a word handed to one of them is
# a word about that field rather than a loose string.
READERS = {"of_kind": "kind", "names": "kind", "startswith": "", "endswith": ""}


def spoken(source: str, found: dict[str, set[str]]) -> None:
    """Record the words one rule module decides on, filed under the field it reads them against.

    A rule branches on a small closed vocabulary and then writes English about what it found, so
    drawing a fact field from the second set explores nothing. Reading the comparisons, the
    collections a membership test asks about, and the readers a rule calls is what separates the
    words that decide an answer from the words that describe one, and the attribute standing
    opposite each comparison is what says which field the word belongs to.
    """

    def keep(node: ast.expr, name: str) -> None:
        match node:
            case ast.Constant(value=str() as word) if MATCHED.match(word):
                found.setdefault(name, set()).add(word)
                found.setdefault("", set()).add(word)
            case ast.Set(elts=elements) | ast.Tuple(elts=elements) | ast.List(elts=elements):
                for element in elements:
                    keep(element, name)
            case _:
                return

    def read(node: ast.expr) -> str:
        """Return the field name one operand of a comparison stands for, if it names one."""
        match node:
            case ast.Attribute(attr=attribute):
                return attribute
            case ast.Call(func=ast.Attribute(value=receiver, attr=method)) if method in READERS:
                return READERS[method] or read(receiver)
            case _:
                return ""

    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Compare(left=left, comparators=comparators):
                name = read(left) or next((read(item) for item in comparators if read(item)), "")
                keep(left, name)
                for item in comparators:
                    keep(item, name)
            case ast.Call(func=ast.Attribute(attr=method) as callee, args=arguments) if (
                method in READERS
            ):
                for item in arguments:
                    keep(item, read(callee))
            case ast.Set() | ast.Tuple() | ast.List():
                keep(node, "")
            case _:
                continue


@cache
def vocabulary(family: type[Fact]) -> dict[str, tuple[str, ...]]:
    """Return the words the rules that read one family decide their answers on, by field.

    A generic alphabet is what makes a schema-derived sweep shallower than it looks. A rule opening
    with `if subject.kind != "callable"` answers zero for every fact a random string could build,
    so the sweep runs its first line forever and a mutation to the rest of the body survives it.
    The vocabulary is read out of the rule modules themselves, so a rule that starts matching a new
    word is explored the run after it is written.
    """
    found: dict[str, set[str]] = {"": set(NEUTRAL)}
    for rule in built_catalog().rules:
        if family_of(rule) is family:
            spoken(Path(import_module(rule.module).__file__ or "").read_text(), found)
    return {name: tuple(sorted(words | {""})) for name, words in found.items()}


@cache
def facts_of(family: type[Fact]) -> st.SearchStrategy[Fact]:
    """Return the strategy building well-formed facts of one family, cached per family."""
    return SchemaStrategy(dialect=vocabulary(family)).of(family)
