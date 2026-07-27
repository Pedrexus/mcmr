import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import anyio
from pydantic import JsonValue, NonNegativeInt, field_serializer

from .bases import FrozenFlexModel
from .catalog import Catalog
from .discovery import RuleModuleDiscovery
from .engine import RuleEngine
from .kernel import Kernel
from .models import EngineStats, Observation, RuleDefinition, RuleValue
from .policy import Boolean, Category, Numeric, Policy, Profile, RulePolicy, Verdict
from .protocol import KernelStats

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# How many findings one failing site writes into a run record. A snapshot is taken on every run,
# so the record states the shape of a failure rather than reproducing the whole report.
KEPT = 3


class RecordedFinding(FrozenFlexModel):
    """What one finding leaves behind in a run record, which is what it said and where.

    The measurements and the repair stay out on purpose. Running the rule again recomputes both,
    while the sentence and the location are what a later comparison needs in order to say which
    finding it is looking at, and a snapshot written on every run has to stay a file somebody can
    open.
    """

    message: str
    where: str


class FailingSite(FrozenFlexModel):
    """One site a rule failed at, beside the value it read there and what it said about it.

    A count of failures says a repository got worse and nothing more. The site says where, and the
    value says by how much, which is what separates a finding that moved from one that grew. The
    findings say which thing, for the rules that have migrated to reporting them.
    """

    fact: str
    value: RuleValue
    findings: tuple[RecordedFinding, ...] = ()
    finding_count: NonNegativeInt = 0


class RuleRecord(FrozenFlexModel):
    """What one rule concluded over a whole repository in one run.

    The bar travels with the rule. A value only means something beside what the profile was willing
    to accept, so a record that kept the number and dropped the policy would let a later comparison
    subtract two figures that were never held to the same standard. Keeping both is what lets that
    comparison notice and say so instead.
    """

    rule: str
    contract: str
    policy: RulePolicy | None = None
    observations: NonNegativeInt = 0
    unassessed: NonNegativeInt = 0
    failing: tuple[FailingSite, ...] = ()

    @property
    def judgment(self) -> str:
        """Return the fingerprint of what this rule measured and the bar it was held to.

        The bar is folded in as the shape it takes and the allowance it renders rather than as its
        own serialization, because a set of accepted categories iterates in whatever order this
        process hashed it into, and a fingerprint that moved between two processes would report a
        rule as redefined every other run.
        """
        bar = f"{type(self.policy).__name__}:{allowed(self.policy)}"
        return hashlib.sha256(f"{self.contract}|{bar}".encode()).hexdigest()[:16]

    @property
    def sites(self) -> dict[str, FailingSite]:
        """Return every site this rule failed at, keyed by the site."""
        return {site.fact: site for site in self.failing}

    @field_serializer("policy")
    def canonical(self, policy: RulePolicy | None) -> dict[str, JsonValue] | None:
        """Write the bar with any set of accepted categories sorted.

        A set has no order of its own, so writing it as it iterates would give two runs over
        unchanged source two different files, and a store a reader diffs has to hold still.
        """
        if policy is None:
            return None
        written: dict[str, JsonValue] = policy.model_dump(mode="json")
        return {
            name: sorted(value, key=str) if isinstance(value, list) else value
            for name, value in written.items()
        }


class RunIdentity(FrozenFlexModel):
    """Say which tree a run judged and when it judged it.

    A repository outside version control still records a run and leaves the commit empty, since
    refusing to snapshot an untracked tree would be a worse answer than an honest blank. A dirty
    tree is marked, because the commit alone would name source that was never judged.
    """

    taken_at: str
    commit: str = ""
    branch: str = ""
    is_dirty: bool = False

    @property
    def label(self) -> str:
        """Return the short name a report calls this run by."""
        return f"{self.commit[:7] or 'untracked'}{'*' if self.is_dirty else ''}"


class RunStats(FrozenFlexModel):
    """Measure how much of a repository one run looked at.

    Only counts live here. A duration belongs to the machine that ran the analysis rather than to
    the repository it judged, and a record two runs are compared through has to hold still.
    """

    file_count: NonNegativeInt = 0
    fact_count: NonNegativeInt = 0
    invocation_count: NonNegativeInt = 0


class RunRecord(FrozenFlexModel):
    """One whole judgment of a repository, kept so a later one can be held against it.

    The version is a literal rather than a number, so a record this release cannot read is refused
    at validation instead of being read as though the fields still meant what they used to.
    """

    version: Literal[1] = 1
    profile: str
    identity: RunIdentity
    stats: RunStats = RunStats()
    rules: tuple[RuleRecord, ...] = ()

    @property
    def catalog(self) -> str:
        """Return the fingerprint of every rule this run judged and every bar it applied."""
        pairs = sorted(f"{record.rule}={record.judgment}" for record in self.rules)
        return hashlib.sha256("\n".join(pairs).encode()).hexdigest()[:16]

    @property
    def failing_count(self) -> int:
        """Return how many sites failed anywhere in this run."""
        return sum(len(record.failing) for record in self.rules)

    @property
    def failing_rule_count(self) -> int:
        """Return how many rules failed anywhere in this run."""
        return sum(1 for record in self.rules if record.failing)

    @property
    def unassessed_count(self) -> int:
        """Return how many observations no policy in this profile was able to judge."""
        return sum(record.unassessed for record in self.rules)

    def index(self) -> dict[str, RuleRecord]:
        """Return every rule of this run keyed by its identifier."""
        return {record.rule: record for record in self.rules}


class GitIdentity(FrozenFlexModel):
    """Read which commit a checkout sits on, so a run can say which tree it judged."""

    root: Path

    def read(self, moment: datetime) -> RunIdentity:
        """Return the identity of the tree as it stands at one moment.

        The moment is written to the millisecond in one fixed width, so the runs of a repository
        sort into the order they happened by their text alone. Two runs a second apart would
        otherwise be indistinguishable, and the series would be drawn in whatever order the commits
        happened to hash into.
        """
        return RunIdentity(
            taken_at=f"{moment.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z",
            commit=self.describe("rev-parse", "HEAD"),
            branch=self.describe("branch", "--show-current"),
            is_dirty=bool(self.describe("status", "--porcelain")),
        )

    def describe(self, *arguments: str) -> str:
        """Return what one git query answers, or nothing at all when it cannot answer."""
        completed = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return "" if completed.returncode else completed.stdout.strip()


class RunStore(FrozenFlexModel):
    """Keep the runs a repository has recorded, as one readable file each.

    `.mcmr` already holds the evidence a project states about itself, so the judgments it has
    recorded belong beside that rather than in a directory of their own. One file per run keeps the
    store diffable and lets a reader drop a run by deleting a file, and the name carries the moment
    and the commit so a plain listing is already the series in the order it happened.
    """

    directory: Path

    @property
    def runs(self) -> Path:
        """Return the directory the recorded runs live in."""
        return self.directory / "runs"

    def write(self, record: RunRecord) -> Path:
        """Write one run and return the file that now holds it."""
        self.runs.mkdir(parents=True, exist_ok=True)
        compact = record.identity.taken_at.replace("-", "").replace(":", "")
        target = self.runs / f"{compact}-{record.identity.commit[:7] or 'untracked'}.json"
        target.write_text(record.model_dump_json(indent=2) + "\n")
        return target

    def read(self, path: Path) -> RunRecord:
        """Return the run one file holds, refusing anything this release cannot read."""
        return RunRecord.model_validate_json(path.read_text())

    def records(self) -> tuple[RunRecord, ...]:
        """Return every recorded run, oldest first, or nothing when none were recorded."""
        found = sorted(self.runs.glob("*.json")) if self.runs.is_dir() else []
        return tuple(
            sorted(
                (self.read(path) for path in found),
                key=lambda record: (record.identity.taken_at, record.identity.commit),
            )
        )

    def latest(self, profile: str) -> RunRecord | None:
        """Return the newest run recorded under one profile, if the store holds one."""
        under = [record for record in self.records() if record.profile == profile]
        return under[-1] if under else None


class Assessment(FrozenFlexModel):
    """One rule, one fact it read, and the verdict a profile reached about the value."""

    definition: RuleDefinition
    observation: Observation
    verdict: Verdict


class Verdicts(FrozenFlexModel):
    """Everything one pass of the engine concluded, before anyone decides how to report it.

    A reader wants the failures right now and a record wants the same judgment in a form a later
    run can be held against. Both read this, so the two answers can never disagree about what the
    repository was found to be.
    """

    profile: Profile
    selection: tuple[RuleDefinition, ...] = ()
    assessments: tuple[Assessment, ...] = ()
    kernel: KernelStats = KernelStats()
    engine: EngineStats

    @property
    def failures(self) -> tuple[Assessment, ...]:
        """Return every assessment the profile judged as a failure."""
        return tuple(item for item in self.assessments if item.verdict is Verdict.FAIL)

    @property
    def unassessed_count(self) -> int:
        """Return how many observations this profile stated no policy for."""
        return sum(1 for item in self.assessments if item.verdict is Verdict.UNASSESSED)

    def record(self, identity: RunIdentity) -> RunRecord:
        """Return this judgment as the run record a later comparison reads.

        Every selected rule is recorded, including one that never met a fact, because a rule the
        catalog held is exactly what a later run has to know in order to tell a rule that was added
        since apart from one that regressed.
        """
        gathered: dict[str, list[Assessment]] = {
            definition.id: [] for definition in self.selection
        }
        for item in self.assessments:
            gathered[item.definition.id].append(item)
        return RunRecord(
            profile=self.profile.name,
            identity=identity,
            stats=RunStats(
                file_count=self.kernel.file_count,
                fact_count=self.kernel.fact_count,
                invocation_count=self.engine.invocation_count,
            ),
            rules=tuple(
                self.rule(definition, gathered[definition.id])
                for definition in sorted(self.selection, key=lambda item: item.id)
            ),
        )

    @staticmethod
    def site(observation: Observation) -> FailingSite:
        """Return what a record keeps about one site, which is bounded on purpose.

        A rule reporting a hundred findings at one site would grow the store faster than anybody
        could read it, so the record keeps the first few in the order the rule stated them and says
        how many there were, and nothing is silently lost.
        """
        return FailingSite(
            fact=observation.fact,
            value=observation.value,
            findings=tuple(
                RecordedFinding(message=finding.message, where=finding.span.location)
                for finding in observation.findings[:KEPT]
            ),
            finding_count=len(observation.findings),
        )

    def rule(self, definition: RuleDefinition, judged: Sequence[Assessment]) -> RuleRecord:
        """Return what one rule concluded, with the sites it failed at in a stable order."""
        failing = sorted(
            (self.site(item.observation) for item in judged if item.verdict is Verdict.FAIL),
            key=lambda site: site.fact,
        )
        return RuleRecord(
            rule=definition.id,
            contract=contract(definition),
            policy=stated(self.profile.policy(definition)),
            observations=len(judged),
            unassessed=sum(1 for item in judged if item.verdict is Verdict.UNASSESSED),
            failing=tuple(failing),
        )


class Judgment(FrozenFlexModel):
    """Run the catalog over a repository once and say what every selected rule concluded."""

    binary: Path
    root: Path
    profile: Profile
    select: str = ""
    suffixes: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()

    def run(self) -> Verdicts:
        """Build the facts the selected rules read, execute them, and judge every value."""
        catalog = Catalog(modules=RuleModuleDiscovery().modules)
        identity = {definition.callable: definition for definition in catalog.definitions}
        rules = [rule for rule in catalog.rules if self.select in rule.callable_path]
        workspace = Kernel(
            binary=self.binary, root=self.root, exclude=self.exclude, suffixes=self.suffixes
        ).run(rules)
        engine = RuleEngine(rules=workspace.runnable(rules), fixes=catalog.fixes)
        report = anyio.run(engine.run, workspace.streams)
        return Verdicts(
            profile=self.profile,
            selection=tuple(identity[rule.callable_path] for rule in rules),
            assessments=tuple(
                Assessment(
                    definition=identity[item.rule],
                    observation=item,
                    verdict=self.profile.decide(identity[item.rule], item.value),
                )
                for item in report.observations
            ),
            kernel=workspace.stats,
            engine=report.stats,
        )


def contract(definition: RuleDefinition) -> str:
    """Return the fingerprint of what one rule measures, ignoring how it documents itself.

    Only the fields that decide what a value means are folded in. A rewritten docstring leaves two
    runs comparable, while a different fact family, result shape, unit, category set, or default
    setting does not, because each of those changes the number rather than the prose around it.
    """
    parts = [
        definition.id,
        definition.fact,
        definition.output,
        definition.unit,
        ",".join(sorted(definition.categories)),
        ",".join(f"{name}={value}" for name, value in sorted(definition.settings.items())),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def stated(policy: Policy | None) -> RulePolicy | None:
    """Return the bar a profile applies, in one of the three shapes a record can carry.

    Every policy this release ships is one of those three, and a record has to say which one held
    a value, so a fourth shape is refused here rather than quietly recorded as a rule that nothing
    judged.
    """
    if policy is None or isinstance(policy, Numeric | Boolean | Category):
        return policy
    raise TypeError(f"a run record cannot carry a {type(policy).__name__} policy")


def allowed(policy: Policy | None) -> str:
    """Render what a profile accepts for one rule, for a report."""
    match policy:
        case Numeric(minimum=None, maximum=maximum):
            return f"<= {maximum:g}"
        case Numeric(minimum=minimum, maximum=None):
            return f">= {minimum:g}"
        case Numeric(minimum=minimum, maximum=maximum):
            return f"{minimum:g}..{maximum:g}"
        case Boolean(expected=expected):
            return str(expected)
        case Category(accepted=accepted):
            return ", ".join(sorted(accepted))
        case _:
            return ""


def section(title: str, entries: Iterable[str], limit: int) -> list[str]:
    """Return one titled block of a report, bounded, stating its own count and truncation."""
    listed = list(entries)
    shown = listed[:limit]
    omitted = len(listed) - len(shown)
    return [
        "",
        f"{title} ({len(listed)})",
        *(f"  {entry}" for entry in shown),
        *([f"  and {omitted} more"] if omitted else []),
    ]
