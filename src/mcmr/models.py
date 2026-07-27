import inspect
from abc import ABC, abstractmethod
from annotationlib import Format
from collections import OrderedDict
from collections.abc import Awaitable, Mapping
from enum import StrEnum, auto
from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Annotated,
    Literal,
    Protocol,
    TypeAliasType,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import Field, NonNegativeInt, PositiveInt, SkipValidation

from .bases import FrozenFlexModel
from .facts import Fact, NodeRef, SourceSpan, SymbolRef

if TYPE_CHECKING:
    from .backends import RuleDependency


class FixSafety(StrEnum):
    """Describe how confidently MCMR may apply one fix."""

    SAFE = auto()
    REVIEW = auto()


class Unit(StrEnum):
    """Identify the scale carried by one numeric rule value."""

    COUNT = auto()
    PERCENTAGE = auto()


class RuleLane(StrEnum):
    """Identify how one rule reaches its answer, which its identifier has to carry.

    A deterministic rule reads structure and gives the same answer twice. A GLiNER rule asks a
    small extraction model. An LLM rule asks for a judgment. Those are three different things to
    trust, so a reader looking at a finding needs to know which one produced it without opening
    the catalog.

    The lane owns the leading digit of every rule number, which is what keeps two lanes in one
    family from minting the same identifier. That happened: `general/llm/errors/r0001` and
    `general/deterministic/errors/r0001` both derived `ALL-ERRO0001`, and the catalog refused to
    build until one of them moved. Reserving the digit makes the collision impossible rather than
    caught.
    """

    DETERMINISTIC = auto()
    GLINER = auto()
    LLM = auto()

    @property
    def slot(self) -> str:
        """Return the digit every rule number in this lane begins with."""
        return {RuleLane.DETERMINISTIC: "0", RuleLane.GLINER: "1", RuleLane.LLM: "2"}[self]


class RuleScope(StrEnum):
    """Identify the language a rule answers for, or that it answers for every language.

    A language scope carries the exact name a provider labels its facts with, so the engine can
    reject a mismatch without a second mapping table. A general rule accepts every language.
    """

    GENERAL = auto()
    PYTHON = auto()
    RUST = auto()
    TYPESCRIPT = auto()
    C = auto()
    CPP = auto()
    CUDA = auto()

    @property
    def prefix(self) -> str:
        """Return the identifier prefix rules in this scope carry."""
        return {
            RuleScope.GENERAL: "ALL",
            RuleScope.PYTHON: "PY",
            RuleScope.RUST: "RS",
            RuleScope.TYPESCRIPT: "TS",
            RuleScope.C: "C",
            RuleScope.CPP: "CPP",
            RuleScope.CUDA: "CU",
        }[self]


type Count = Annotated[int, Unit.COUNT]
type Occurrence = Annotated[bool, Unit.COUNT]
type Percentage = Annotated[float, Unit.PERCENTAGE]
type RuleValue = bool | int | float | str
type RuleSetting = RuleValue | tuple[str, ...] | frozenset[str]


class RewriteKind(StrEnum):
    """Identify which typed source operation one rewrite requests."""

    REMOVE = auto()
    REPLACE = auto()
    MOVE = auto()
    UNWRAP = auto()
    RENAME = auto()
    INLINE = auto()


class Placement(StrEnum):
    """Identify which side of an anchor receives a moved or inserted node."""

    BEFORE = auto()
    AFTER = auto()


class Rewrite(FrozenFlexModel, ABC):
    """Request one typed source operation the language backend renders and applies."""

    @property
    @abstractmethod
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return every span this rewrite touches, so the engine can detect overlap."""


class Remove(Rewrite):
    """Delete one node together with the separators and trivia that only exist to hold it."""

    kind: Literal[RewriteKind.REMOVE] = RewriteKind.REMOVE
    target: NodeRef

    @property
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return the removed node span."""
        return (self.target.span,)


class Replace(Rewrite):
    """Replace one node with source the backend parses before it writes anything."""

    kind: Literal[RewriteKind.REPLACE] = RewriteKind.REPLACE
    target: NodeRef
    source: str

    @property
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return the replaced node span."""
        return (self.target.span,)


class Move(Rewrite):
    """Relocate one existing node beside an anchor without rewriting its source."""

    kind: Literal[RewriteKind.MOVE] = RewriteKind.MOVE
    target: NodeRef
    anchor: NodeRef
    placement: Placement

    @property
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return the moved node span and its destination anchor span."""
        return (self.target.span, self.anchor.span)


class Unwrap(Rewrite):
    """Replace one node with a descendant it already contains."""

    kind: Literal[RewriteKind.UNWRAP] = RewriteKind.UNWRAP
    target: NodeRef
    keep: NodeRef

    @property
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return the unwrapped node span."""
        return (self.target.span,)


class Rename(Rewrite):
    """Rename one resolved symbol at its declaration and at every reference bound to it."""

    kind: Literal[RewriteKind.RENAME] = RewriteKind.RENAME
    symbol: SymbolRef
    name: str

    @property
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return the declaration span and every reference span the rename edits."""
        return (
            self.symbol.declaration.span,
            *(reference.span for reference in self.symbol.references),
        )


class Inline(Rewrite):
    """Replace every reference to one declaration with its body, then remove the declaration.

    Three fixes reached for the same two operations in the same order, which is what a refactoring
    looks like before it has a name. Stating it as one operation is what lets the backend keep the
    body and the references consistent: it parses the body once, adapts it at each site, and either
    every site and the declaration change together or none of them do.
    """

    kind: Literal[RewriteKind.INLINE] = RewriteKind.INLINE
    declaration: NodeRef
    body: NodeRef
    references: list[NodeRef]

    @property
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return the declaration span and every reference span this inlining edits."""
        return (
            self.declaration.span,
            *(reference.span for reference in self.references),
        )


type SourceRewrite = Annotated[
    Remove | Replace | Move | Unwrap | Rename | Inline,
    Field(discriminator="kind"),
]


class FixPlan(FrozenFlexModel):
    """Describe one atomic fix as an ordered rewrite program.

    A plan is all-or-nothing. The backend renders every rewrite against the parsed tree, reparses
    the result, and keeps the edits only when the file still parses and the rule that produced the
    plan no longer reports the finding. A plan always carries at least one rewrite, because a fix
    that found nothing to change produces no plan rather than an empty one.
    """

    summary: str
    rewrites: list[SourceRewrite] = Field(min_length=1)

    @property
    def spans(self) -> tuple[SourceSpan, ...]:
        """Return every span this plan edits, in rewrite order."""
        return tuple(span for rewrite in self.rewrites for span in rewrite.spans)


class Measurement(FrozenFlexModel):
    """One named number behind a finding, which is the arithmetic a reader would redo by hand.

    A rule answers with one value, and that value is almost never the only number it computed.
    Naming the parts is what lets a report say a class declares forty-eight members of which
    twelve nobody reads, rather than repeating the single number the policy compared.
    """

    name: str
    value: float
    unit: Unit = Unit.COUNT

    @property
    def rendered(self) -> str:
        """Return this measurement as the phrase a report prints beside a finding.

        Four significant figures is where a measurement stops being read and starts being decoded,
        so a share carried to six decimal places is written the way somebody would say it.
        """
        amount = f"{self.value:.4g}%" if self.unit is Unit.PERCENTAGE else f"{self.value:.4g}"
        return f"{self.name} {amount}"


def counted(amount: int, singular: str, plural: str = "") -> str:
    """Return one number beside its noun, in whichever number the amount asks for.

    Every finding message states a quantity and most of those quantities can be one, so the
    alternative is a catalog that writes `1 lines` wherever it happens to be right once.
    """
    return f"{amount} {singular}" if amount == 1 else f"{amount} {plural or singular + 's'}"


class RepairKind(StrEnum):
    """Identify whether a finding is closed by an edit or by a decision somebody makes."""

    EDIT = auto()
    CHOICE = auto()


class Repair(FrozenFlexModel, ABC):
    """State how one finding is put right.

    Only two answers are honest. Either the repair is a program the backend can render, or it is a
    judgment that belongs to whoever owns the code. Offering the second as though it were the first
    is how a tool teaches people to distrust it, so the two are different types rather than one
    optional patch.
    """

    @property
    @abstractmethod
    def summary(self) -> str:
        """Return the one line a report shows beside the finding."""


class Edit(Repair):
    """Close one finding by applying the rewrites a language backend renders."""

    kind: Literal[RepairKind.EDIT] = RepairKind.EDIT
    plan: FixPlan
    safety: FixSafety = FixSafety.SAFE

    @property
    def summary(self) -> str:
        """Return what the plan says it does, which is the fix's own first line."""
        return self.plan.summary


class Choice(Repair):
    """Name the decision a reader has to make where no edit can be proven right."""

    kind: Literal[RepairKind.CHOICE] = RepairKind.CHOICE
    question: str
    options: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        """Return the question, with the answers it is a choice between when it names any."""
        return f"{self.question} ({' or '.join(self.options)})" if self.options else self.question


type FindingRepair = Annotated[Edit | Choice, Field(discriminator="kind")]


class Finding(FrozenFlexModel):
    """Say what one rule found, exactly where it found it, and what would change it.

    A scalar answers how much and nothing else. This answers which thing, by how much, and what to
    do, which is the difference between a report a reader can act on and a number they have to
    reverse engineer from the rule body.
    """

    message: str
    span: SourceSpan
    measurements: tuple[Measurement, ...] = ()
    repair: FindingRepair | None = None


class Reported[Value: RuleValue](FrozenFlexModel):
    """One rule value beside the findings that explain it.

    This is the whole migration seam. A rule that answers with a bare `Count` keeps working exactly
    as it did, and a rule that has evidence to state wraps the same value in this and hands its
    findings along with it. The value is still the only thing a policy judges, so adding evidence
    can never move a verdict.
    """

    value: Value
    findings: tuple[Finding, ...] = ()


class Answer(Protocol):
    """Expose one rule value beside its findings, whatever produced the pair.

    The engine reads answers through this rather than through `Reported` itself, because a rule
    states its exact value type and an invariant model would then refuse to be an answer at all.
    Reading both members and writing neither is what makes one shape hold every rule.
    """

    @property
    def value(self) -> RuleValue: ...

    @property
    def findings(self) -> tuple[Finding, ...]: ...


type CountReport = Annotated[Reported[int], Unit.COUNT]
type OccurrenceReport = Annotated[Reported[bool], Unit.COUNT]
type PercentageReport = Annotated[Reported[float], Unit.PERCENTAGE]
type RuleAnswer = RuleValue | Answer
type RuleOutcome = RuleAnswer | Awaitable[RuleAnswer]


class Function[**P, Result](Protocol):
    """Expose the callable and source identity every declared function provides."""

    __module__: str
    __qualname__: str

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Result: ...


class Fix[**P](FrozenFlexModel):
    """Keep one fix callable and its source-derived relationship to a rule.

    A fix states the rewrites it wants and nothing else. Whether those rewrites amount to a plan is
    not its decision: a fix that finds nothing to change returns no rewrites, and this wrapper is
    what turns that into the absence of a plan. Its own documentation is the summary, since the
    sentence describing what a fix does and the sentence shown beside its diff are the same
    sentence.
    """

    function: SkipValidation[Function[P, list[SourceRewrite]]]
    module: str
    qualname: str
    rule_callable: str
    is_default: bool = False
    safety: FixSafety = FixSafety.SAFE

    @cached_property
    def signature(self) -> inspect.Signature:
        """Return the fix signature used for contract compatibility."""
        return inspect.signature(self.function, annotation_format=Format.FORWARDREF)

    @cached_property
    def summary(self) -> str:
        """Return the one line this fix states about itself."""
        return (inspect.getdoc(self.function) or "").split("\n", 1)[0]

    def plan(self, rewrites: list[SourceRewrite]) -> FixPlan | None:
        """Return the plan these rewrites make, or nothing when there are none."""
        if not rewrites:
            return None
        return FixPlan(summary=self.summary, rewrites=rewrites)

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> FixPlan | None:
        """Invoke the wrapped fix and return the plan its rewrites make."""
        return self.plan(self.function(*args, **kwargs))

    def invoke(self, subject: Fact, settings: Mapping[str, RuleSetting]) -> FixPlan | None:
        """Bind one injected fact and explicit settings before fix execution."""
        bound = self.signature.bind(subject, **settings)
        return self.plan(self.function(*bound.args, **bound.kwargs))


class FixDecorator[**P](Protocol):
    """Preserve one fix function with the same inputs as its rule."""

    def __call__(self, candidate: Function[P, list[SourceRewrite]]) -> Fix[P]: ...


class Rule[**P, Result: RuleOutcome](FrozenFlexModel):
    """Keep one rule callable and expose its source-linked fix decorator."""

    function: SkipValidation[Function[P, Result]]
    module: str
    qualname: str

    @property
    def callable_path(self) -> str:
        """Return the source-derived callable identity."""
        return f"{self.module}.{self.qualname}"

    @cached_property
    def signature(self) -> inspect.Signature:
        """Return the source signature used for injection and settings."""
        return inspect.signature(self.function)

    @cached_property
    def hints(self) -> dict[str, type]:
        """Return evaluated annotations including numeric result metadata."""
        return get_type_hints(self.function, include_extras=True)

    @property
    def raw_documentation(self) -> str:
        """Return the complete source docstring without changing its sections."""
        return inspect.getdoc(self.function) or ""

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Result:
        """Invoke the wrapped rule through its original typed contract."""
        return self.function(*args, **kwargs)

    @cached_property
    def subject(self) -> str:
        """Return the name of the fact parameter every rule declares first."""
        return next(iter(self.signature.parameters))

    @cached_property
    def injected(self) -> tuple[tuple[str, type], ...]:
        """Return the name and declared type of every explicitly injected input."""
        parameters = list(self.signature.parameters.values())
        return tuple(
            (parameter.name, self.hints[parameter.name])
            for parameter in parameters[1:]
            if parameter.default is inspect.Parameter.empty
        )

    def invoke(
        self,
        subject: Fact,
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
    ) -> RuleOutcome:
        """Call the rule with one fact, its typed dependencies, and explicit settings.

        The catalog already proved this signature, so the arguments are placed against it
        directly rather than rematched for every fact in the stream.
        """
        arguments: OrderedDict[str, Fact | RuleDependency | RuleSetting] = OrderedDict(
            {self.subject: subject}
        )
        arguments.update((name, dependencies[hint]) for name, hint in self.injected)
        arguments.update(settings)
        bound = inspect.BoundArguments(self.signature, arguments)
        return self.function(*bound.args, **bound.kwargs)

    def fix(
        self,
        *,
        is_default: bool = False,
        safety: FixSafety = FixSafety.SAFE,
    ) -> FixDecorator[P]:
        """Create a decorator linking one compatible fix to this rule."""

        def register(candidate: Function[P, list[SourceRewrite]]) -> Fix[P]:
            return Fix(
                function=candidate,
                module=candidate.__module__,
                qualname=candidate.__qualname__,
                rule_callable=self.callable_path,
                is_default=is_default,
                safety=safety,
            )

        return register


class RuleContract(Protocol):
    """Expose runtime rule metadata without erasing typed call signatures to `Any`."""

    @property
    def injected(self) -> tuple[tuple[str, type], ...]: ...

    @property
    def module(self) -> str: ...

    @property
    def qualname(self) -> str: ...

    @property
    def callable_path(self) -> str: ...

    @property
    def signature(self) -> inspect.Signature: ...

    @property
    def hints(self) -> dict[str, type]: ...

    @property
    def raw_documentation(self) -> str: ...

    def invoke(
        self,
        subject: Fact,
        *,
        settings: Mapping[str, RuleSetting],
        dependencies: Mapping[type, RuleDependency],
    ) -> RuleOutcome: ...


class FixContract(Protocol):
    """Expose runtime fix metadata independently from its typed function wrapper."""

    @property
    def module(self) -> str: ...

    @property
    def qualname(self) -> str: ...

    @property
    def rule_callable(self) -> str: ...

    @property
    def is_default(self) -> bool: ...

    @property
    def safety(self) -> FixSafety: ...

    @property
    def signature(self) -> inspect.Signature: ...

    def invoke(self, subject: Fact, settings: Mapping[str, RuleSetting]) -> FixPlan | None: ...


type OutputContract = tuple[str, str, list[str]]


class Pending(FrozenFlexModel):
    """Retain one asynchronous rule result the event loop still has to await."""

    rule: SkipValidation[RuleContract]
    subject: SkipValidation[Fact]
    outcome: SkipValidation[Awaitable[RuleAnswer]]
    contract: OutputContract


class RuleDocumentation(FrozenFlexModel):
    """Retain the complete reStructuredText documentation of one rule."""

    summary: str
    definition: str
    evidence: str = ""
    exceptions: str = ""
    examples: str
    references: list[str] = []


class FixDefinition(FrozenFlexModel):
    """Describe one validated fix attached to a catalog rule."""

    name: str
    callable: str
    is_default: bool
    safety: FixSafety


class RuleDefinition(FrozenFlexModel):
    """Describe one source-derived rule contract."""

    id: str
    callable: str
    scope: RuleScope
    lane: str
    family: str
    fact: str
    output: str
    unit: str = ""
    categories: list[str] = []
    settings: dict[str, str] = {}
    documentation: RuleDocumentation
    fixes: list[FixDefinition] = []


class Observation(FrozenFlexModel):
    """Retain one rule value beside the fact that received it and the evidence behind it.

    The value is what a policy judges and the findings are what a reader reads. A rule that states
    no findings leaves the tuple empty, which is what lets the two halves of the catalog travel
    through one shape while the migration runs.
    """

    rule: str
    fact: str
    value: RuleValue
    span: SourceSpan = SourceSpan(path="")
    findings: tuple[Finding, ...] = ()


class EngineStats(FrozenFlexModel):
    """Measure only the framework work performed by the mock engine."""

    rule_count: NonNegativeInt
    skipped_rule_count: NonNegativeInt = 0
    fact_count: NonNegativeInt
    invocation_count: NonNegativeInt
    provider_read_count: NonNegativeInt
    fix_count: NonNegativeInt
    fix_candidate_count: NonNegativeInt
    planning_nanoseconds: NonNegativeInt
    execution_nanoseconds: NonNegativeInt
    fix_planning_nanoseconds: NonNegativeInt
    total_nanoseconds: NonNegativeInt


class EngineReport(FrozenFlexModel):
    """Return mock observations with explicit framework timings."""

    observations: list[Observation] = []
    stats: EngineStats


class FloorReport(FrozenFlexModel):
    """Summarize repeated mock framework measurements."""

    samples: PositiveInt
    fact_count: PositiveInt
    rule_count: PositiveInt
    cold_discovery_nanoseconds: PositiveInt
    warm_discovery_nanoseconds: PositiveInt
    median_planning_nanoseconds: PositiveInt
    median_execution_nanoseconds: PositiveInt
    median_fix_planning_nanoseconds: PositiveInt
    median_total_nanoseconds: PositiveInt


def output_contract(annotation: type | TypeAliasType) -> OutputContract:
    """Resolve output kind, unit, and categories from one return annotation."""
    if isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    if get_origin(annotation) is Annotated:
        value, *metadata = get_args(annotation)
        unit = next((str(item) for item in metadata if isinstance(item, Unit)), "")
        output, _, categories = output_contract(value)
        return output, unit, categories
    if isinstance(annotation, type) and issubclass(annotation, Reported):
        return output_contract(reported_value(annotation))
    if get_origin(annotation) is Literal:
        return "category", "", [str(item) for item in get_args(annotation)]
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return "category", "", [str(item) for item in annotation]
    return annotation.__name__, "", []


def answered(outcome: RuleAnswer) -> RuleValue:
    """Return the value one rule answered with, whichever of the two shapes it used.

    This is the one place that reads a value out of an answer, so a rule that has migrated to
    reporting findings and a rule that has not are indistinguishable to everything downstream.
    """
    return outcome if isinstance(outcome, bool | int | float | str) else outcome.value


def explained(outcome: RuleAnswer) -> tuple[Finding, ...]:
    """Return the findings one rule stated, which is nothing at all for a bare scalar."""
    return () if isinstance(outcome, bool | int | float | str) else outcome.findings


def declared(annotation: type | TypeAliasType) -> type | TypeAliasType:
    """Return the type one return annotation states, with any alias and any unit peeled off."""
    if isinstance(annotation, TypeAliasType):
        annotation = annotation.__value__
    if get_origin(annotation) is Annotated:
        peeled: type | TypeAliasType = get_args(annotation)[0]
        return peeled
    return annotation


def reports_findings(annotation: type | TypeAliasType) -> bool:
    """Whether a rule with this return annotation answers with findings beside its value.

    This is the one test of whether a rule has migrated, so the engine, the mock backend, and the
    guard that tracks the migration all agree about which half of the catalog a rule is in.
    """
    carried = declared(annotation)
    return isinstance(carried, type) and issubclass(carried, Reported)


def reported_value(annotation: type[FrozenFlexModel]) -> type | TypeAliasType:
    """Return the value type one reported answer carries, which is what a policy will judge.

    The argument is read from the parametrization rather than from the field, because a generic
    model keeps its own annotation as the variable it was declared with and only the metadata
    remembers what a rule filled that variable in with.
    """
    carried: type | TypeAliasType = annotation.__pydantic_generic_metadata__["args"][0]
    return carried


def fact_type(annotation: type) -> type[Fact]:
    """Require one concrete fact model as the first rule input."""
    if not isinstance(annotation, type) or not issubclass(annotation, Fact):
        raise TypeError(f"Rule input {annotation!r} must be a Fact type")
    return annotation
