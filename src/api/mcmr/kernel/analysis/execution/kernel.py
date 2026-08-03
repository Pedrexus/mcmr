import sys
from time import perf_counter_ns
from typing import TYPE_CHECKING, cast

from pydantic_core import SchemaValidator, core_schema

from ....facts import Fact, SymbolReachFact
from ...protocol import KernelArgument, KernelClient, KernelStats, KernelStreamBatch
from .catalog import buildable, requested_facts
from .workspace import FamilyStream, Workspace

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Mapping, Sequence

    from ....domain.contracts import RuleContract


class _KernelRuntime:
    """Own stream validation and the kernel client that consumes it."""

    class Reader:
        """Validate one native fact stream and enforce its family contract."""

        def __init__(self, *, types: Mapping[str, type[Fact]]) -> None:
            self.types = types
            self.validators = {
                name: SchemaValidator(core_schema.list_schema(family.__pydantic_core_schema__))
                for name, family in types.items()
            }
            self.seen: set[str] = set()
            self.started = perf_counter_ns()
            self.validation_nanoseconds = 0

        @staticmethod
        def request(
            *, families: Sequence[str], suffixes: Sequence[str]
        ) -> dict[str, KernelArgument]:
            """Build the native request envelope for one analysis pass."""
            request: dict[str, KernelArgument] = {
                "families": list(families),
                "python_standard_library": sorted(sys.stdlib_module_names),
            }
            if suffixes:
                request["suffixes"] = list(suffixes)
            return request

        def batch(self, answer: KernelStreamBatch) -> FamilyStream:
            """Validate one batch under the family named by the provider."""
            family = self.types.get(answer.family)
            if family is None:
                raise RuntimeError(
                    f"the analysis kernel returned unexpected fact family {answer.family}"
                )
            self.seen.add(answer.family)
            started = perf_counter_ns()
            facts = cast(
                "list[Fact]",
                self.validators[answer.family].validate_json(answer.payload),
            )
            self.validation_nanoseconds += perf_counter_ns() - started
            return FamilyStream(family=family, facts=facts)

        def footer(self, stats: KernelStats) -> KernelStats:
            """Complete timing after proving every family arrived."""
            if missing := set(self.types) - self.seen:
                names = ", ".join(sorted(missing))
                raise RuntimeError(f"the analysis kernel omitted fact families {names}")
            return stats.model_copy(
                update={
                    "total_nanoseconds": perf_counter_ns() - self.started,
                    "fact_validation_nanoseconds": self.validation_nanoseconds,
                }
            )

        def read(
            self, answers: Iterable[KernelStreamBatch | KernelStats]
        ) -> Generator[FamilyStream | KernelStats]:
            """Yield validated batches followed by completed statistics."""
            for answer in answers:
                yield (
                    self.footer(answer) if isinstance(answer, KernelStats) else self.batch(answer)
                )

    class Kernel(KernelClient):
        """Build exactly the fact families required by the selected rules."""

        suffixes: tuple[str, ...] = ()

        @staticmethod
        def collect(items: Generator[FamilyStream | KernelStats]) -> Workspace:
            """Collect streamed fact batches and statistics into one workspace."""
            streams: dict[type[Fact], list[Fact]] = {}
            stats = KernelStats()
            for item in items:
                if isinstance(item, KernelStats):
                    stats = item
                else:
                    streams.setdefault(item.family, []).extend(item.facts)
            return Workspace(streams=streams, stats=stats)

        def build(self, families: Sequence[str], types: Mapping[str, type[Fact]]) -> Workspace:
            """Ask the kernel for these families and collect their streams."""
            return self.collect(self.build_streams(families, types))

        def build_streams(
            self, families: Sequence[str], types: Mapping[str, type[Fact]]
        ) -> Generator[FamilyStream | KernelStats]:
            """Validate and yield each declared family from one kernel pass."""
            reader = _KernelRuntime.Reader(types=types)
            request = reader.request(families=families, suffixes=self.suffixes)
            yield from reader.read(super().stream(request))

        def reach(self) -> Workspace:
            """Build the graph and return how far each declaration's use spreads."""
            return self.build(
                [SymbolReachFact.__name__],
                {SymbolReachFact.__name__: SymbolReachFact},
            )

        def requested(self, rules: Sequence[RuleContract]) -> dict[str, type[Fact]]:
            """Return selected fact families that this kernel can build."""
            required = {family for rule in rules for family in requested_facts(rule)}
            families = buildable()
            return {fact.__name__: fact for fact in required if fact.__name__ in families}

        def run(self, rules: Sequence[RuleContract]) -> Workspace:
            """Build requested families and validate them into frozen fact models."""
            requested = self.requested(rules)
            return self.build(sorted(requested), requested) if requested else Workspace()

        def sections(self, rules: Sequence[RuleContract]) -> Generator[FamilyStream | KernelStats]:
            """Yield each usable family and final aggregate statistics."""
            requested = self.requested(rules)
            yield from (
                self.build_streams(sorted(requested), requested) if requested else (KernelStats(),)
            )


Kernel = _KernelRuntime.Kernel
