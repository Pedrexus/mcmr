import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from .bases import FrozenFlexModel
from .facts import (
    AttributeAccessFact,
    AutomationTaskFact,
    BranchFact,
    CallFact,
    ClassFact,
    CloneGroupFact,
    CollectionFact,
    CommentFact,
    ComprehensionFact,
    DependencyComponentFact,
    DirectoryFact,
    EnumFact,
    ExceptionFact,
    Fact,
    FunctionFact,
    ImportBindingFact,
    InteropFact,
    KernelLaunchFact,
    LiteralGroupFact,
    MethodGroupFact,
    ModuleCouplingFact,
    ModuleFact,
    ModuleSurfaceFact,
    OverrideFact,
    ParameterFact,
    ProjectConfigurationFact,
    ProseSegmentFact,
    PydanticModelFact,
    QueryFact,
    RepositoryHistoryFact,
    RouteFact,
    RuntimeTypeCheckFact,
    RustSurfaceFact,
    StringExpressionFact,
    SymbolFact,
    SymbolReachFact,
    SyntaxFact,
    TestCaseGroupFact,
    TestFunctionFact,
    TestSuiteFact,
    TryBlockFact,
    TypeAnnotationFact,
    WaiverFact,
)
from .models import fact_type
from .protocol import KernelArgument, KernelClient, KernelStats

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pydantic import JsonValue

    from .models import RuleContract


def buildable() -> dict[str, type[Fact]]:
    """Return every fact family the analysis kernel knows how to build, by name."""
    return {
        fact.__name__: fact
        for fact in (
            AttributeAccessFact,
            AutomationTaskFact,
            BranchFact,
            CallFact,
            ClassFact,
            CloneGroupFact,
            CollectionFact,
            CommentFact,
            ComprehensionFact,
            DependencyComponentFact,
            DirectoryFact,
            EnumFact,
            ExceptionFact,
            FunctionFact,
            ImportBindingFact,
            InteropFact,
            KernelLaunchFact,
            LiteralGroupFact,
            MethodGroupFact,
            ModuleCouplingFact,
            ModuleFact,
            ModuleSurfaceFact,
            OverrideFact,
            ParameterFact,
            ProjectConfigurationFact,
            ProseSegmentFact,
            PydanticModelFact,
            QueryFact,
            RepositoryHistoryFact,
            RouteFact,
            RuntimeTypeCheckFact,
            RustSurfaceFact,
            StringExpressionFact,
            SymbolFact,
            SymbolReachFact,
            SyntaxFact,
            TestCaseGroupFact,
            TestFunctionFact,
            TestSuiteFact,
            TryBlockFact,
            TypeAnnotationFact,
            WaiverFact,
        )
    }


VENDORED = (
    "**/.git/**",
    "**/.venv/**",
    "**/node_modules/**",
    "**/__pycache__/**",
    "**/.chefe/**",
    "**/target/**",
    "**/build/**",
    "**/dist/**",
    "**/.pixi/**",
    "**/site-packages/**",
    "**/.mypy_cache/**",
    "**/.ruff_cache/**",
    "**/vendored/**",
    "research/their-papers/**",
    "research/my-papers/**",
)


class Workspace(FrozenFlexModel):
    """Hold the fact streams one kernel run produced, keyed by their exact fact type."""

    streams: dict[type[Fact], list[Fact]] = {}
    stats: KernelStats = KernelStats()

    def runnable(self, rules: Sequence[RuleContract]) -> list[RuleContract]:
        """Return the rules whose fact stream this workspace actually holds."""
        return [rule for rule in rules if requested_fact(rule) in self.streams]

    def stream[FactType: Fact](self, family: type[FactType]) -> list[FactType]:
        """Return one family's facts, typed as that family.

        The workspace stores every stream under one fact base so the engine can plan over all of
        them together. A caller that wants one family back gets it narrowed here, which also
        rejects a stream a provider filed under the wrong type.
        """
        return [fact for fact in self.streams.get(family, []) if isinstance(fact, family)]


class Kernel(KernelClient):
    """Ask the analysis kernel for exactly the fact families the selected rules read.

    The rules decide the request. Each one declares its fact type as its first parameter, so the
    planner takes those types, asks for those families, and hands each stream back to the rules
    that named it. A family nobody selected is never built, never parsed for, and never sent.
    """

    suffixes: tuple[str, ...] = ()

    def requested(self, rules: Sequence[RuleContract]) -> dict[str, type[Fact]]:
        """Return the fact families the selected rules read and this kernel can build."""
        required = {requested_fact(rule) for rule in rules}
        families = buildable()
        return {fact.__name__: fact for fact in required if fact.__name__ in families}

    def run(self, rules: Sequence[RuleContract]) -> Workspace:
        """Build the requested families and validate them into their frozen fact models."""
        requested = self.requested(rules)
        if not requested:
            return Workspace()
        retained = EvidenceStore(directory=self.root / ".mcmr").streams(
            [
                fact
                for fact in {requested_fact(rule) for rule in rules}
                if fact not in requested.values()
            ]
        )
        built = self.build(sorted(requested), requested)
        return built.model_copy(update={"streams": {**built.streams, **retained}})

    def reach(self) -> Workspace:
        """Build the repository graph and return how far each declaration's use spreads."""
        return self.build(["SymbolReachFact"], {SymbolReachFact.__name__: SymbolReachFact})

    def build(self, families: list[str], types: dict[str, type[Fact]]) -> Workspace:
        """Ask the kernel for exactly these families and validate what it returns."""
        request: dict[str, KernelArgument] = {"families": families}
        if self.suffixes:
            request["suffixes"] = list(self.suffixes)
        answered = self.ask(request)
        with ThreadPoolExecutor() as workers:
            pending = {
                types[name]: workers.submit(_validate_stream, types[name], values)
                for name, values in answered.facts.items()
            }
        return Workspace(
            streams={family: future.result() for family, future in pending.items()},
            stats=answered.stats,
        )


class EvidenceStore(FrozenFlexModel):
    """Read the fact streams a repository retains as records rather than as source.

    Some evidence is not in the code. A runbook, an alert, a data catalog entry, and a release
    record are engineering artifacts a project keeps, and no parser can derive them. A project
    states them as `.mcmr/<FactName>.json`, holding one fact or a list of them, and they arrive
    through the same typed contract as everything the kernel builds. Nothing found means those
    rules are skipped, which is the honest answer rather than a guessed one.
    """

    directory: Path

    def streams(self, families: Sequence[type[Fact]]) -> dict[type[Fact], list[Fact]]:
        """Return the retained facts for every requested family that has a record."""
        return {
            family: [family.model_validate(item) for item in self.records(family)]
            for family in families
            if (self.directory / f"{family.__name__}.json").exists()
        }

    def records(self, family: type[Fact]) -> list[object]:
        """Return the raw records one family file holds, as a list either way."""
        content = json.loads((self.directory / f"{family.__name__}.json").read_text())
        return content if isinstance(content, list) else [content]


def requested_fact(rule: RuleContract) -> type[Fact]:
    """Return the fact type one rule declares as its first parameter."""
    return fact_type(rule.hints[next(iter(rule.signature.parameters))])


def _validate_stream(family: type[Fact], records: list[JsonValue]) -> list[Fact]:
    """Validate one independent fact family for the kernel client."""
    return [family.model_validate(record) for record in records]


def locate(root: Path) -> Path:
    """Return the kernel binary built from this checkout, or the one on the path."""
    candidates = (
        root / "kernel" / "target" / "release" / "mcmr-kernel",
        root / "kernel" / "target" / "debug" / "mcmr-kernel",
    )
    return next((path for path in candidates if path.exists()), Path("mcmr-kernel"))
