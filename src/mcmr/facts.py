from collections import Counter
from enum import StrEnum, auto
from functools import cached_property
from statistics import fmean
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import (
    BeforeValidator,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    model_validator,
)

from .bases import FrozenFlexModel, FrozenRootModel

if TYPE_CHECKING:
    from collections.abc import Iterator

type Ratio = Annotated[float, Field(ge=0.0, le=1.0)]


class Visibility(StrEnum):
    """Name how widely one declaration reaches, however its language spells that.

    A provider maps its own language onto these four levels: a declaration keyword in Java, C#,
    Kotlin, or C++, a `pub` qualifier in Rust, an `export` or `#` prefix in TypeScript, an
    identifier's case in Go, and the leading-underscore convention in Python.
    """

    PUBLIC = auto()
    PROTECTED = auto()
    INTERNAL = auto()
    PRIVATE = auto()


class MemberKind(StrEnum):
    """Name what one declared type member is in terms every object language shares."""

    CONSTRUCTOR = auto()
    DESTRUCTOR = auto()
    PROPERTY = auto()
    STATIC_METHOD = auto()
    CLASS_METHOD = auto()
    METHOD = auto()
    FIELD = auto()


class ReceiverKind(StrEnum):
    """Name whose member one access reads, relative to the accessing scope."""

    SELF = auto()
    OWNER = auto()
    SUPER = auto()
    OTHER = auto()


class LiteralKind(StrEnum):
    """Name the shape one expression carries when the source states it literally."""

    NONE = auto()
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    MAPPING = auto()
    SEQUENCE = auto()


class SourceSpan(FrozenFlexModel):
    """Locate one fact in source or retained engineering evidence."""

    path: str
    start_line: PositiveInt = 1
    start_column: NonNegativeInt = 0
    end_line: PositiveInt = 1
    end_column: NonNegativeInt = 0

    @property
    def location(self) -> str:
        """Return the one string a reader pastes into an editor to arrive here.

        A span covering several lines states both ends, because the range is what says whether a
        finding is about one statement or about the whole declaration around it.
        """
        if self.end_line > self.start_line:
            return f"{self.path}:{self.start_line}-{self.end_line}"
        return f"{self.path}:{self.start_line}"


class NodeRef(FrozenFlexModel):
    """Address one resolved syntax node and retain the exact source it spans.

    A fix names the nodes it edits through these handles, so a rewrite stays a typed request the
    language backend renders rather than a byte range a rule computed on its own.
    """

    id: str
    span: SourceSpan
    kind: str = ""
    text: str = ""


class SymbolRef(FrozenFlexModel):
    """Address one resolved declaration together with every reference bound to it."""

    id: str
    name: str
    declaration: NodeRef
    references: list[NodeRef] = []
    are_references_complete: bool = False


class Evidence(FrozenFlexModel):
    """Retain one provider claim supporting a named rule measurement."""

    signal: str
    detail: str
    source: str
    confidence: Ratio = 1.0


class Relation(FrozenFlexModel):
    """Relate two named units of one repository, which is what a graph edge is.

    Both ends have to be named in one vocabulary, and stating that as a type is what lets a test
    hold every provider to it. An edge list spelling its sources as file paths and its targets as
    package names is a graph with no path through it, so a rule computing components over one
    answers zero forever and reads exactly like a clean repository.
    """

    source: str
    target: str


class Fact(FrozenFlexModel):
    """Identify one independently invalidated unit supplied to rules."""

    key: str
    span: SourceSpan
    language: str | None = None
    evidence: list[Evidence] = []


class ChecklistItem(FrozenFlexModel):
    """Retain named observable checks for one in-scope engineering item."""

    name: str
    checks: dict[str, bool] = {}
    is_in_scope: bool = True


class Checklist(FrozenRootModel):
    """Measure named checks over one independently scoped collection."""

    root: list[ChecklistItem]

    @classmethod
    def from_value(cls, value: Checklist | list[ChecklistItem]) -> Checklist:
        """Accept an existing checklist or validate one concise item list."""
        if isinstance(value, list):
            return cls(root=value)
        return value

    def coverage(self, *required_checks: str) -> float:
        """Return the percentage of in-scope items satisfying every requested check."""
        items = [item for item in self.root if item.is_in_scope]
        if not items:
            return 0.0
        complete = sum(
            all(item.checks.get(check, False) for check in required_checks) for item in items
        )
        return complete / len(items) * 100.0


class LengthDistribution(FrozenRootModel):
    """Provide derived statistics for one measured length distribution."""

    root: list[int]

    @classmethod
    def from_value(cls, value: LengthDistribution | list[int]) -> LengthDistribution:
        """Accept an existing distribution or validate one concise integer list."""
        if isinstance(value, list):
            return cls(root=value)
        return value

    def __len__(self) -> int:
        """Return the number of measured values."""
        return len(self.root)

    def at_least(self, minimum: int) -> LengthDistribution:
        """Return values meeting one inclusive measurement floor."""
        return LengthDistribution(root=[value for value in self.root if value >= minimum])

    def uniformity(self) -> float:
        """Return inverse normalized mean absolute deviation as a percentage."""
        if not self.root:
            return 0.0
        mean = fmean(self.root)
        deviation = fmean(abs(value - mean) for value in self.root)
        return max(0.0, 1.0 - deviation / mean) * 100.0


type ChecklistValue = Annotated[Checklist, BeforeValidator(Checklist.from_value)]
type LengthDistributionValue = Annotated[
    LengthDistribution,
    BeforeValidator(LengthDistribution.from_value),
]


class ImportBindingFact(Fact):
    """Describe one imported binding and its resolved qualifying uses."""

    name: str
    module: str
    imported_name: str = ""
    importer_module: str = ""
    declaration: NodeRef | None = None
    module_node: NodeRef | None = None
    reference_count: NonNegativeInt = 0
    has_qualifying_use: bool = False
    is_external: bool = False
    is_reexported: bool = False
    is_type_only: bool = False
    has_documented_side_effect: bool = False
    is_relative: bool = False
    is_project_owned: bool = False
    is_sole_binding: bool = False
    has_private_module_component: bool = False
    is_private_member: bool = False
    is_private_uppercase_constant: bool = False
    is_wildcard: bool = False
    is_generated: bool = False
    is_vendored: bool = False


class AbstractionFact(Fact):
    """Describe one abstraction and the code that depends on its contract."""


class AlertFact(Fact):
    """Describe one operational alert and its response metadata."""

    alerts: ChecklistValue = Checklist(root=[])


class AlgorithmFact(Fact):
    """Describe one algorithm and its measured resource behavior."""


class ArchitectureBoundaryFact(Fact):
    """Describe one intended boundary and the dependencies crossing it."""


class ArchitectureCharacteristicFact(Fact):
    """Describe one declared architecture characteristic and its evidence."""

    characteristics: list["ArchitectureCharacteristic"] = []


class ArchitectureCharacteristic(FrozenFlexModel):
    """Retain objective evidence for one declared architecture quality."""

    name: str
    has_objective: bool
    has_executable_check: bool
    has_retained_result: bool
    has_owner: bool
    has_scope: bool
    observation_age_days: NonNegativeInt
    is_in_ci: bool = False
    is_automatable: bool = True
    has_repeatable_review: bool = False


class AttributeAccessFact(Fact):
    """Describe one resolved attribute access and its owning scope."""

    accesses: list["AttributeAccess"] = []


class AttributeAccess(FrozenFlexModel):
    """Retain one member access, its declared visibility, and its lexical owner relationship."""

    name: str
    receiver_kind: ReceiverKind
    visibility: Visibility = Visibility.PUBLIC
    is_inside_owning_class: bool = False
    is_protocol_name: bool = False
    receiver_text: str = ""
    receiver_type: str = ""
    receiver_type_bases: list[str] = []
    node: NodeRef | None = None


class AuthorshipSignalFact(Fact):
    """Describe one measurable signal associated with machine-authored prose."""

    segments: list["AuthorshipSegment"] = []
    assessment: "AuthorshipAssessment | None" = None


class AuthorshipSegment(FrozenFlexModel):
    """Retain external style patterns for one eligible prose segment."""

    identifier: str
    patterns_by_provider: dict[str, list[str]] = {}
    is_eligible: bool = True


class AuthorshipAssessment(FrozenFlexModel):
    """Retain one provider signal and the provider's eligibility floor."""

    provider: str
    signal: Literal["human_like", "ai_like", "mixed", "inconclusive"]
    observed_word_count: NonNegativeInt
    minimum_word_count: NonNegativeInt


class AuthorityGrantFact(Fact):
    """Describe one authority grant and the scope receiving it."""


class AutomationTaskFact(Fact):
    """Describe one repeatable engineering task and its automation entry point."""

    tasks: list["AutomationTask"] = []


class AutomationTask(FrozenFlexModel):
    """Describe one repository-owned command for a lifecycle capability."""

    capability: str
    commands: list[str] = []
    is_repository_owned: bool = True
    is_noninteractive: bool = True


class BackupFact(Fact):
    """Describe one backup and its retained recovery evidence."""


class BenchmarkFact(Fact):
    """Describe one reproducible performance benchmark."""


class ControlKind(StrEnum):
    """Name one control-flow structure in terms every imperative language shares."""

    CONDITIONAL = auto()
    ALTERNATIVE = auto()
    LOOP = auto()
    SWITCH = auto()
    CATCH = auto()
    JUMP = auto()
    RECURSION = auto()
    SEQUENCE = auto()


class BranchFact(Fact):
    """Describe one conditional structure and the arms it selects between."""

    chains: list["ConditionalChain"] = []


class ConditionalChain(FrozenFlexModel):
    """Retain one chain of conditions tested in sequence and what each arm does."""

    subject: str = ""
    arms: list["ConditionalArm"] = []
    has_fallback: bool = False
    node: NodeRef | None = None


class ConditionalArm(FrozenFlexModel):
    """Retain one arm of a conditional chain and the exact comparison that selects it."""

    comparison: str = ""
    literal: str = ""
    statement_count: NonNegativeInt = 0
    returns_value: bool = False
    reads_subject_only: bool = True


class CallFact(Fact):
    """Describe one resolved callable invocation."""

    calls: list["CallSite"] = []
    module_bindings: list[str] = []

    @cached_property
    def call_counts(self) -> Counter[str]:
        """Index resolved qualified call names on first use."""
        return Counter(call.qualified_name for call in self.calls)

    def count_calls(self, *qualified_names: str) -> int:
        """Count resolved calls matching any supplied qualified name."""
        return sum(self.call_counts[name] for name in qualified_names)


class Expression(FrozenFlexModel):
    """Retain one resolved expression and the nested calls that produced its value.

    This is the shared primitive behind every call rule that used to receive a precomputed
    verdict or a normalized pattern string. A provider resolves names, literal shapes, and
    nesting; the vocabulary of interesting names stays inside the rule that owns it.
    """

    text: str = ""
    qualified_name: str = ""
    literal_kind: LiteralKind = LiteralKind.NONE
    resolved_type: str = ""
    arguments: list["Expression"] = []
    entries: list["MappingEntry"] = []
    node: NodeRef | None = None

    def producers(self) -> list[Expression]:
        """Return this expression and every nested expression under it, outermost first."""
        return [self, *(nested for item in self.arguments for nested in item.producers())]

    def produced_by(self, *qualified_names: str) -> bool:
        """Whether this expression or anything it nests resolves to one of ``qualified_names``."""
        wanted = set(qualified_names)
        return any(item.qualified_name in wanted for item in self.producers())


class MappingEntry(FrozenFlexModel):
    """Retain one key and value of a literal mapping the source states directly."""

    key: str
    value: Expression


class CallSite(FrozenFlexModel):
    """Retain one resolved call and source facts shared by call-based rules."""

    qualified_name: str
    path: str
    arguments: list[Expression] = []
    keyword_names: list[str] = []
    receiver: Expression | None = None
    assigned_target: str = ""
    result_is_discarded: bool = False
    node: NodeRef | None = None
    callee: NodeRef | None = None
    is_external: bool = False
    is_standard_library: bool = False
    is_first_party: bool = False
    is_constructor: bool = False
    is_shadowed: bool = False
    has_ambiguous_alias: bool = False
    is_decorator_factory: bool = False
    has_starred_arguments: bool = False
    enclosing_is_async: bool = False


class ChangeFact(Fact):
    """Describe one related set of source changes."""

    changes: ChecklistValue = Checklist(root=[])


class CIConfigurationFact(Fact):
    """Describe one continuous integration configuration."""

    workflows: list["CIWorkflow"] = []


class CIWorkflow(FrozenFlexModel):
    """Describe one parsed workflow and the protections it actually runs."""

    name: str
    tasks: list[str] = []
    triggers: list[str] = []
    is_change_blocking: bool = False
    uses_locked_dependencies: bool = True
    has_explicit_permissions: bool = True
    cancels_superseded_runs: bool = True


class CICheckFact(Fact):
    """Describe one check executed by continuous integration."""

    checks: list["CICheck"] = []


class CICheck(FrozenFlexModel):
    """Describe one CI check and its measured duration percentile."""

    name: str
    duration_percentile_seconds: NonNegativeFloat
    percentile: Ratio = 0.9
    is_required: bool = True
    is_change_blocking: bool = True


class ClassFact(Fact):
    """Describe one class and its resolved members."""

    classes: list["ClassAnalysis"] = []
    coupled_groups: list["CoupledTypeGroup"] = []
    model_files: list["ModelFile"] = []
    projection_groups: list["AttributeProjection"] = []
    has_approved_model_foundation_policy: bool = False


def rank(order: tuple[str, ...], value: str) -> int:
    """Return where one value sits in a declared order, after all of it when it is unlisted.

    A project states the visibilities and member kinds it sorts by, and a language can declare a
    member the project never listed, such as a destructor or a field. Sorting those after every
    listed one keeps them stable instead of refusing to sort the class at all.
    """
    return order.index(value) if value in order else len(order)


class MethodAnalysis(FrozenFlexModel):
    """Retain ordering and binding facts for one directly declared method."""

    name: str
    region: NonNegativeInt = 0
    kind: MemberKind = MemberKind.METHOD
    visibility: Visibility = Visibility.PUBLIC
    decorators: list[str] = []
    is_protocol_name: bool = False
    owner_qualified_calls: list[str] = []

    def order_key(
        self,
        *,
        lifecycle: tuple[str, ...],
        visibility_order: tuple[str, ...],
        kind_order: tuple[str, ...],
        alphabetical: bool,
    ) -> tuple[int, int, int, str]:
        """Return the sort position this method should hold under one declared member order.

        Lifecycle names come first in their declared sequence, language protocol members follow,
        and every remaining member sorts by visibility, then by kind, then optionally by name.
        """
        if self.name in lifecycle:
            return (0, lifecycle.index(self.name), 0, "")
        if self.is_protocol_name:
            return (1, 0, 0, self.name.casefold() if alphabetical else "")
        return (
            2,
            rank(visibility_order, self.visibility),
            rank(kind_order, self.kind),
            self.name.casefold() if alphabetical else "",
        )


class ClassAnalysis(FrozenFlexModel):
    """Retain one class and closed-world graph properties used by class rules."""

    name: str
    path: str
    span: SourceSpan | None = None
    scope: Literal["module", "nested"] = "module"
    visibility: Visibility = Visibility.PUBLIC
    direct_bases: list[str] = []
    decorators: list[str] = []
    class_keywords: list[str] = []
    methods: list[MethodAnalysis] = []
    has_explicit_registry_name: bool = False
    has_instance_fields: bool = False
    field_count: NonNegativeInt = 0
    direct_subclasses: list[str] = []
    descendant_count: NonNegativeInt = 0
    is_instantiated: bool = False
    is_exported: bool = False
    only_cross_module_reference_is_subclass: bool = False
    is_pass_through_layer: bool = False
    base_is_removable_overlap: bool = False
    has_redundant_direct_base: bool = False
    has_noncooperative_concrete_collision: bool = False
    duplicate_component_alias_count: NonNegativeInt = 0
    is_declarative_model: bool = False
    has_ordinary_behavior: bool = False
    importing_modules: list[str] = []
    proposed_model_destination: str = ""
    directly_inherits_pydantic_base_model: bool = False
    inherits_approved_model_foundation: bool = False


class CoupledTypeGroup(FrozenFlexModel):
    """Retain short co-imported role types sharing a stable name prefix."""

    prefix: str
    role_suffixes: list[str] = []
    type_count: NonNegativeInt
    maximum_type_lines: NonNegativeInt
    coimporting_module_count: NonNegativeInt


class ModelFile(FrozenFlexModel):
    """Retain one implementation file below a shared models directory."""

    path: str
    top_level_class_count: NonNegativeInt
    model_class_count: NonNegativeInt
    is_package_initializer: bool = False


class AttributeProjection(FrozenFlexModel):
    """Retain matching key and attribute projections from one typed root."""

    root: str
    attribute_names: list[str] = []
    output_keys: list[str] = []


class CloneGroupFact(Fact):
    """Describe one group of structurally similar source fragments.

    Detection is token normalized rather than textual, so a copy survives renamed locals and
    reformatting. What arrives is where every copy sits and how long the repeated run is, together
    with the size of the tree it was found in, so a rule can weigh one clone against the whole
    repository without asking for a second fact.
    """

    fragments: list["CloneFragment"] = []
    token_length: NonNegativeInt = 0
    repository_line_count: NonNegativeInt = 0

    @model_validator(mode="after")
    def fit_inside_repository(self) -> Self:
        """Require the repeated lines to fit inside the repository they measure."""
        if self.redundant_line_count > self.repository_line_count:
            raise ValueError(
                f"clone group repeats {self.redundant_line_count} lines inside a repository "
                f"holding {self.repository_line_count}"
            )
        return self

    @property
    def copy_count(self) -> int:
        """Return how many places state this fragment."""
        return len(self.fragments)

    @property
    def line_count(self) -> int:
        """Return the lines one copy covers, taking the tightest copy as the claim."""
        return min((fragment.line_count for fragment in self.fragments), default=0)

    @property
    def redundant_line_count(self) -> int:
        """Return the lines that exist only because this fragment was copied."""
        return self.line_count * max(self.copy_count - 1, 0)


class CloneFragment(FrozenFlexModel):
    """Retain one copy of a repeated fragment and the lines it covers."""

    path: str
    start_line: PositiveInt = 1
    end_line: PositiveInt = 1
    line_count: NonNegativeInt = 0


class CollectionFact(Fact):
    """Describe one collection expression and its uses."""

    pair_sequences: list["PairSequence"] = []
    local_collections: list["LocalCollection"] = []


class PairSequence(FrozenFlexModel):
    """Retain one literal pair sequence and its resolved lookup-only reads."""

    pair_count: NonNegativeInt
    keys_are_unique_literals: bool
    has_single_assignment: bool
    all_reads_are_lookup_loops: bool


class LocalCollection(FrozenFlexModel):
    """Retain one local literal collection and its representation-sensitive uses."""

    name: str = ""
    kind: Literal["list", "tuple"]
    value_count: NonNegativeInt
    has_homogeneous_literals: bool
    all_reads_are_iteration: bool = False
    all_reads_are_membership: bool = False
    values_are_unique: bool = False


class CommentFact(Fact):
    """Describe one contiguous source comment."""

    groups: list["CommentGroup"] = []


class CommentGroup(FrozenFlexModel):
    """Retain measured sizes for one contiguous comment group."""

    line_count: PositiveInt
    character_count: NonNegativeInt
    token_count: NonNegativeInt
    parses_as_source: bool = False
    is_directive: bool = False
    node: NodeRef | None = None

    def size(self, measure: str) -> int:
        """Read one supported size using the configured scale."""
        match measure:
            case "tokens":
                return self.token_count
            case "characters":
                return self.character_count
            case "lines":
                return self.line_count
            case _:
                raise ValueError(f"Unsupported comment measure {measure!r}")


class ComponentFact(Fact):
    """Describe one architectural component and its public surface."""


class ComprehensionFact(Fact):
    """Describe one comprehension and its nested clauses."""

    loop_counts: list[NonNegativeInt] = []
    set_loop_candidates: list["SetLoopCandidate"] = []


class SetLoopCandidate(FrozenFlexModel):
    """Retain one set initialization followed by a structurally convertible loop."""

    name: str = ""
    has_unshadowed_set_initialization: bool
    loop_is_synchronous: bool
    only_effect_is_add: bool
    conditional_count: NonNegativeInt = 0
    has_else: bool = False
    initialization: NodeRef | None = None
    loop: NodeRef | None = None
    element: NodeRef | None = None
    target: NodeRef | None = None
    iterable: NodeRef | None = None
    conditions: list[NodeRef] = []


class DataAssetFact(Fact):
    """Describe one governed data asset."""

    assets: list["DataAsset"] = []


class DataAsset(FrozenFlexModel):
    """Retain one catalog asset and its exact governance metadata."""

    identifier: str
    description: str = ""
    owners: list[str] = []
    domain: str = ""
    is_changed: bool = False
    fields: list["DataField"] = []


class DataField(FrozenFlexModel):
    """Retain one catalog field and its documented type."""

    name: str
    data_type: str
    description: str = ""


class DataAssetReferenceFact(Fact):
    """Describe one resolved reference to a governed data asset."""

    references: list["DataAssetReference"] = []


class DataAssetReference(FrozenFlexModel):
    """Retain one source reference and its exact catalog resolution."""

    source_location: str
    asset_identifier: str
    asset_exists: bool
    lifecycle: Literal["active", "deprecated", "removed", "unknown"] = "unknown"
    upstream_health: dict[str, Literal["healthy", "unhealthy", "unknown"]] = Field(
        default_factory=dict
    )


class DataChangeFact(Fact):
    """Describe one schema or contract change affecting data."""

    changes: list["DataChange"] = []


class DataChange(FrozenFlexModel):
    """Retain one schema change and its transitive impact evidence."""

    asset_identifier: str
    is_breaking: bool
    downstream_assets: list[str] = []
    tested_assets: list[str] = []


class DataFieldReferenceFact(Fact):
    """Describe one resolved reference to a data field."""

    references: list["DataFieldReference"] = []


class DataFieldReference(FrozenFlexModel):
    """Retain one source field reference and exact schema resolution."""

    source_location: str
    asset_identifier: str
    field_name: str
    asset_exists: bool
    field_exists: bool
    expected_type: str = ""
    catalog_type: str = ""


class DecisionRecordFact(Fact):
    """Describe one engineering decision and its retained rationale."""


class DependencyCandidateFact(Fact):
    """Describe one evaluated third-party dependency candidate."""


class DependencyComponentFact(Fact):
    """Describe the import graph of one repository, whose components a rule reads.

    One fact for the whole repository rather than one per file. Whether an import runs inside a
    cycle is a question about several modules at once, and a file cannot see the modules importing
    it, so a per-file edge list can state only what one file happens to hold.
    """

    import_edges: list["DependencyEdge"] = []


class DependencyEdge(Relation):
    """Retain one resolved import between two modules this repository owns.

    Both ends are the qualified module name the repository graph gives them, and the file and line
    are the site that states the import, so a component a rule finds can be pointed at.
    """

    path: str = ""
    line: PositiveInt = 1


class DependencyFact(Fact):
    """Describe one selected dependency and its release metadata."""

    dependencies: list["DependencyRecord"] = []


class DependencyRecord(FrozenFlexModel):
    """Retain exact package and source state from one dependency evidence record."""

    name: str
    resolved_release_day: int | None = None
    latest_compatible_release_day: int | None = None
    latest_compatible_version: str = ""
    project_state: Literal["active", "archived", "deprecated", "quarantined"] = "active"
    is_repository_archived: bool = False
    is_resolved_release_yanked: bool = False
    is_development: bool = False


class DependencyHubFact(Fact):
    """Describe one graph node nominated as a dependency hub."""


class DeploymentFact(Fact):
    """Describe one deployment path and its retained controls."""

    is_applicable: bool = True
    reproducibility_checks: dict[str, bool] = {}


class DesignStructureFact(Fact):
    """Describe one design structure and its responsibilities."""


class DirectoryFact(Fact):
    """Describe one project directory and its retained entries."""

    visible_entry_count: NonNegativeInt = 0
    source_depth: NonNegativeInt = 0
    direct_module_count: NonNegativeInt = 0
    is_ignored: bool = False
    is_retained: bool = False
    is_definition_catalog: bool = False


class EnumFact(Fact):
    """Describe one enumeration and its members."""

    enums: list["EnumAnalysis"] = []
    scopes: list["EnumScope"] = []
    files: list["EnumFile"] = []


class EnumAnalysis(FrozenFlexModel):
    """Retain one standard enum declaration and its literal members."""

    name: str
    kind: Literal["enum", "int_enum", "str_enum", "flag", "int_flag"]
    members: list["EnumMember"] = []
    overrides_generate_next_value: bool = False


class EnumMember(FrozenFlexModel):
    """Retain one explicit value and the standard auto result at that position."""

    name: str
    explicit_value: str | int
    standard_auto_value: str | int
    value_node: NodeRef | None = None


class EnumScope(FrozenFlexModel):
    """Retain enum reuse inside one narrow common package."""

    destination: str
    enum_count: NonNegativeInt
    reused_enum_count: NonNegativeInt
    cross_module_import_count: NonNegativeInt


class EnumFile(FrozenFlexModel):
    """Retain the top-level shape and reuse of one file under an enums directory."""

    path: str
    top_level_class_count: NonNegativeInt
    enum_class_count: NonNegativeInt
    is_package_initializer: bool = False
    is_shared_across_unrelated_branches: bool = False


class ExceptionFact(Fact):
    """Describe one exception declaration and its uses."""

    exceptions: list["ExceptionUsage"] = []


class ExceptionUsage(FrozenFlexModel):
    """Retain one project exception and its ordinary importing modules."""

    name: str
    defining_module: str
    importing_modules: list[str] = []


class FailurePathFact(Fact):
    """Describe one propagated failure path."""


class FeatureFlagFact(Fact):
    """Describe one feature flag and its lifecycle evidence."""

    flags: list["FeatureFlag"] = []


class FeatureFlag(FrozenFlexModel):
    """Retain one flag's age and explicit lifecycle ownership."""

    name: str
    age_days: NonNegativeInt
    role: str = ""
    owner: str = ""
    has_tested_states: bool = False
    is_past_decision_date: bool = False


class FunctionFact(Fact):
    """Describe one function or method and its resolved body facts."""

    created_task_count: NonNegativeInt = 0
    gather_consumes_created_tasks: bool = False
    gather_returns_exceptions: bool = False
    has_task_group: bool = False
    reads_receiver: bool = False
    cache_decorator: Literal["", "cached_property", "cache", "lru_cache"] = ""
    docstring: str = ""
    recognized_tensor_roles: list[str] = []
    has_tensor_shape_semantics: bool = False
    has_tensor_dtype_semantics: bool = False
    name: str = ""
    scope: Literal["module", "method", "nested"] = "module"
    visibility: Visibility = Visibility.PUBLIC
    is_protocol_name: bool = False
    definition: NodeRef | None = None
    body_expression: NodeRef | None = None
    references: list[NodeRef] = []
    implementation_lines: NonNegativeInt = 0
    direct_statement_count: NonNegativeInt = 0
    reference_count: NonNegativeInt = 0
    behavior_operation_count: NonNegativeInt = 0
    conditional_count: NonNegativeInt = 0
    control_increments: list["ControlIncrement"] = []
    parameters: list["FunctionParameter"] = []
    decorators: list[str] = []
    sole_reference_owner_class: str = ""
    is_async: bool = False
    is_recursive: bool = False
    is_first_class_reference: bool = False
    is_abstract: bool = False
    is_protocol_member: bool = False
    is_overload: bool = False
    is_property: bool = False
    is_framework_hook: bool = False
    is_polymorphic: bool = False
    is_pass_body: bool = False
    is_raise_body: bool = False
    returns_single_call: bool = False
    forwards_only_parameter_unchanged: bool = False
    is_model_method: bool = False
    is_pydantic_validator: bool = False
    checks_raw_input_type: bool = False
    raises_validation_exception: bool = False
    constructs_owner_model: bool = False


class ControlIncrement(FrozenFlexModel):
    """Retain one control-flow structure inside a callable and how deeply it nests.

    This is the shared primitive behind complexity and nesting rules. A provider reports what the
    structure is and where it sits, while each rule owns the model it scores with.
    """

    kind: ControlKind
    nesting_depth: NonNegativeInt = 0


class FunctionParameter(FrozenFlexModel):
    """Describe one resolved function parameter and its call contract."""

    name: str
    type_name: str = ""
    is_positional_only: bool = False
    is_keyword_only: bool = False
    is_receiver: bool = False
    is_required_by_external_contract: bool = False
    has_boolean_annotation: bool = False
    has_boolean_default: bool = False


class HotspotFact(Fact):
    """Describe one graph or history nominated maintenance hotspot."""


class InteropMechanism(StrEnum):
    """Name how one language reaches another."""

    BINARY = auto()
    NATIVE_MODULE = "native-module"
    SHARED_LIBRARY = "shared-library"
    KERNEL = auto()


class InteropFact(Fact):
    """Describe one artifact a repository declares in one language and reaches from another.

    A seam like this appears in no import graph. A Python module spawns a binary a Cargo manifest
    declares, a native extension is bound by an attribute or a macro, and a kernel is loaded by
    name at runtime. Each is a real dependency, and each breaks silently when one side moves.
    """

    name: str
    mechanism: InteropMechanism
    declared_language: str
    referencing_languages: list[str] = []
    references: list["InteropReference"] = []


class InteropReference(FrozenFlexModel):
    """Retain one place that names a cross-language artifact."""

    path: str
    language: str
    line: PositiveInt = 1
    is_literal: bool = True


class InterfaceFact(Fact):
    """Describe one interface and the implementations that depend on it."""


class LineageEdgeFact(Fact):
    """Describe one resolved data lineage edge."""

    edges: list["LineageEdge"] = []


class LineageEdge(FrozenFlexModel):
    """Retain one directed lineage edge and exact endpoint resolution."""

    source: str
    target: str
    source_exists: bool
    target_exists: bool


class LiteralGroupFact(Fact):
    """Describe one group of equal or structurally related literals."""

    string_groups: list["StringLiteralGroup"] = []
    enum_metadata_maps: list["EnumMetadataMap"] = []


class StringLiteralGroup(FrozenFlexModel):
    """Retain exact equal strings sharing one resolved syntax role."""

    value: str
    role: str
    occurrence_count: PositiveInt
    files: list[str] = []
    is_excluded_vocabulary: bool = False


class EnumMetadataMap(FrozenFlexModel):
    """Retain one literal mapping keyed entirely by members of one local enum."""

    enum_name: str
    keys: list[str] = []
    values: list[str] = []
    all_keys_resolve_to_enum: bool = False


class MethodGroupFact(Fact):
    """Describe one related group of methods."""

    groups: list["MethodCloneGroup"] = []


class MethodCloneGroup(FrozenFlexModel):
    """Retain exact sibling method definitions sharing a meaningful base."""

    normalized_definition: str
    locations: list[str] = []
    direct_base: str


class MigrationFact(Fact):
    """Describe one database or data migration."""


class ModuleCoupling(FrozenFlexModel):
    """Retain how many modules one module depends on and how many depend on it.

    Efferent coupling is what this module reaches out to and afferent coupling is what reaches in,
    counted over the modules the repository itself owns. An import of a package nobody here can
    edit is left out of both, since depending on a third-party library says nothing about how this
    architecture holds together.
    """

    module: str = ""
    afferent_count: NonNegativeInt = 0
    efferent_count: NonNegativeInt = 0

    @property
    def instability(self) -> float:
        """Return Martin's `I`, the share of this module's coupling that points outward.

        Zero is a module that only gets depended on, so nothing it reads can force it to change,
        and one is a module that only depends, so every change around it can reach it. A module
        with no internal coupling at all has no ratio to state and reads as zero, which is the
        convention every implementation of this metric shares.
        """
        total = self.afferent_count + self.efferent_count
        return self.efferent_count / total if total else 0.0


class ModuleCouplingFact(ModuleCoupling, Fact):
    """Describe one module as Robert Martin's package metrics see it.

    Four counts arrive and every judgment is left outside. What depends on this module and what it
    depends on give instability, and how much of what it declares is a contract gives abstractness.
    Those two together place the module against the main sequence, which is the line where a module
    is exactly as abstract as it is depended upon.

    A declaration here is a type, since a type is the only thing that can be abstract. Each
    frontend answers for its own language: a Python class deriving `ABC` or `Protocol` or holding
    an `@abstractmethod`, a Rust trait, a C++ or CUDA type declaring a pure virtual. C states no
    contract construct at all, and TypeScript never reaches the repository graph, so neither
    contributes a module here yet.

    The coupling of every module this one imports travels with it, because the Stable Dependencies
    Principle compares two stabilities across one arrow and a rule reading one module at a time
    would otherwise have no way to see the other end.
    """

    declaration_count: NonNegativeInt = 0
    abstract_declaration_count: NonNegativeInt = 0
    dependencies: list[ModuleCoupling] = []

    @property
    def abstractness(self) -> float:
        """Return Martin's `A`, the share of this module's types that state a contract.

        A module declaring no type at all is as concrete as a module can be, so it reads as zero
        rather than as undefined. That is the honest answer for a file of plain functions, which
        offers a caller nothing to implement against.
        """
        if not self.declaration_count:
            return 0.0
        return self.abstract_declaration_count / self.declaration_count

    @property
    def distance(self) -> float:
        """Return Martin's `D`, how far this module sits from the main sequence.

        The main sequence is `A + I = 1`, the line running from maximally abstract and stable to
        maximally concrete and unstable, and `D` is `|A + I - 1|`. Zero is on the line and one is
        as far from it as a module can get, in whichever of the two directions its `A` and `I` say.
        """
        return abs(self.abstractness + self.instability - 1.0)


class ModuleSurfaceFact(Fact):
    """Describe what one module publishes and the escape hatches it uses to do it.

    A module's surface is not what it declares, it is what it re-exports, how deeply its callers
    reach to find it, and how often it steps around its own type system. None of that is visible
    one file at a time, which is why it travels as its own fact.
    """

    star_reexport_count: NonNegativeInt = 0
    star_reexports: list[str] = []
    named_reexport_count: NonNegativeInt = 0
    export_count: NonNegativeInt = 0
    is_index_module: bool = False
    deepest_relative_import: NonNegativeInt = 0
    deepest_relative_specifier: str = ""
    erasable_violations: list["ErasableConstruct"] = []
    escape_hatches: list["EscapeHatch"] = []
    physical_line_count: NonNegativeInt = 0

    @model_validator(mode="after")
    def fit_inside_module(self) -> Self:
        """Require every escape hatch to fit inside the module it measures."""
        if len(self.escape_hatches) > self.physical_line_count:
            raise ValueError(
                f"module holds {len(self.escape_hatches)} escape hatches inside "
                f"{self.physical_line_count} physical lines"
            )
        if any(hatch.line > self.physical_line_count for hatch in self.escape_hatches):
            raise ValueError("module holds an escape hatch beyond its physical lines")
        return self


class ErasableConstruct(FrozenFlexModel):
    """Retain one construct that survives type stripping and so needs a runtime transform."""

    kind: Literal["enum", "const_enum", "namespace", "parameter_property", "import_equals"]
    name: str = ""
    line: PositiveInt = 1


class EscapeHatch(FrozenFlexModel):
    """Retain one place where the source steps around what its type system proved."""

    kind: Literal["assertion", "non_null", "any", "ignore_comment"]
    line: PositiveInt = 1


class ModuleFact(Fact):
    """Describe one source module and its resolved members."""

    constant_placements: list["ConstantPlacement"] = []
    physical_line_count: NonNegativeInt = 0
    class_count: NonNegativeInt = 0
    function_count: NonNegativeInt = 0
    is_package_initializer: bool = False
    has_only_imports_and_all: bool = False
    members: list["ModuleMember"] = []
    is_integration_boundary: bool = False


class ModuleMember(FrozenFlexModel):
    """Describe one module member and its independently classified responsibility."""

    name: str
    responsibility: str


class ConstantPlacement(FrozenFlexModel):
    """Retain one module constant and statements between it and its valid anchor."""

    name: str
    intervening_statement_count: NonNegativeInt = 0


class OnboardingTaskFact(Fact):
    """Describe one task required to onboard a contributor."""

    capabilities: ChecklistValue = Checklist(root=[])


class OperationFact(Fact):
    """Describe one operation and its failure behavior."""


class OperationalRiskFact(Fact):
    """Describe one operational risk and its mitigating evidence."""

    risks: ChecklistValue = Checklist(root=[])


class ParameterFact(Fact):
    """Describe one callable parameter and its uses."""

    parameters: list["ParameterUse"] = []


class ParameterUse(FrozenFlexModel):
    """Retain one annotated parameter and every resolved direct operation."""

    name: str = ""
    owner: str = ""
    span: SourceSpan | None = None
    annotation: str
    operations: list[str] = []
    attribute_reads: list[str] = []
    all_uses_known: bool = True
    is_return_value: bool = False


class PerformanceDecisionFact(Fact):
    """Describe one performance decision and supporting measurements."""

    budgets: ChecklistValue = Checklist(root=[])


class ProjectConfigurationFact(Fact):
    """Describe one project configuration source."""

    assignments: list["ConfigurationAssignment"] = []
    python_target: "PythonTargetConfiguration | None" = None


class ConfigurationAssignment(FrozenFlexModel):
    """Retain one simple collection assignment from project source."""

    name: str
    collection_kind: Literal["list", "tuple", "set", "other"]
    values: list[str] = []
    is_typed_configuration_field: bool = False


class PythonTargetConfiguration(FrozenFlexModel):
    """Retain the normalized Python minor accepted by project and configured tools."""

    project_minimum_minor: int | None = None
    configured_tools: list[str] = []
    tool_target_minors: dict[str, int] = {}
    per_file_target_minors: list[int] = []


class ProseSegmentFact(Fact):
    """Describe one coherent prose segment from source or documentation."""

    sections: list["ProseSection"] = []


class ProseSection(FrozenFlexModel):
    """Retain normalized prose measurements after non-prose blocks are removed."""

    sentence_word_counts: LengthDistributionValue = LengthDistribution(root=[])
    paragraph_word_counts: LengthDistributionValue = LengthDistribution(root=[])
    sentence_openers: list[str] = []


class PydanticModelFact(Fact):
    """Describe one Pydantic model and its validation contract."""

    models: list["PydanticModelAnalysis"] = []


class PydanticModelAnalysis(FrozenFlexModel):
    """Retain validator and constructor structure for one model candidate."""

    name: str
    validators: list["PydanticValidator"] = []
    is_undecorated_plain_class: bool = False
    synchronous_init_count: NonNegativeInt = 0
    fixed_parameter_count: NonNegativeInt = 0
    stored_parameter_count: NonNegativeInt = 0
    validation_count: NonNegativeInt = 0
    default_count: NonNegativeInt = 0
    has_only_data_identity_methods: bool = False


class PydanticValidator(FrozenFlexModel):
    """Retain structural evidence for one imported Pydantic validator."""

    kind: Literal["field", "model_after", "other"]
    fields_read: list[str] = []
    has_self_call: bool = False
    has_nonfield_access: bool = False
    declarative_constraint_count: NonNegativeInt = 0
    proves_disjoint_optional_variants: bool = False
    variant_count: NonNegativeInt = 0


class QueryFact(Fact):
    """Describe one resolved database query."""

    operations: list["QueryOperation"] = []


class QueryOperation(FrozenFlexModel):
    """Retain one resolved SQLAlchemy or SQLModel operation chain."""

    kind: Literal[
        "async_sessionmaker",
        "session_commit",
        "execute_scalars",
        "exec_scalars",
        "primary_key_first",
    ]
    framework: Literal["sqlalchemy", "sqlmodel"]
    is_inside_loop: bool = False
    expire_on_commit: bool = True
    has_unknown_keywords: bool = False
    selected_expression_count: NonNegativeInt = 0
    has_primary_key_equality: bool = False
    has_execution_options: bool = False
    node: NodeRef | None = None
    scalars_segment: NodeRef | None = None
    execute_segment: NodeRef | None = None


class RecoveryPlanFact(Fact):
    """Describe one recovery plan and its exercised evidence."""


class ReleaseFact(Fact):
    """Describe one project or dependency release."""


class RepositoryHistoryFact(Fact):
    """Describe what this repository's own history says about its files and their pairs.

    Every other family reads the code as it stands today. This one reads how it got here, which
    answers two questions the source cannot. A file that is hard to read and keeps being reopened
    is a different and more urgent problem than one that is merely hard to read, and two files that
    keep arriving in the same commit are coupled whatever their imports say.

    Both collections arrive together because they come from one read of the log and are two views
    of the same evidence. What a rule receives is counts rather than verdicts, so the judgment of
    what a busy file or a recurring pair means stays where it belongs.
    """

    commit_count: NonNegativeInt = 0
    files: list["FileHistory"] = []
    pairs: list["CoChangedPair"] = []


class FileHistory(FrozenFlexModel):
    """Retain how often one file changed, how many hands changed it, and how long ago.

    A day count is stated against the newest commit in the window rather than against the clock, so
    two runs over the same history agree. A file the log holds but the tree no longer does keeps
    the changes it earned and reads as no lines at all.
    """

    path: str
    commit_count: NonNegativeInt = 0
    author_count: NonNegativeInt = 0
    days_since_last_change: NonNegativeInt = 0
    line_count: NonNegativeInt = 0
    is_test: bool = False


class CoChangedPair(FrozenFlexModel):
    """Retain two files that keep arriving in the same commit, and what names what.

    The two commit counts are the focused ones, meaning commits small enough to be a real edit
    rather than a sweep, because they are the honest base for asking how often one file brings the
    other along. The reference count is lexical and says how many import lines in either file name
    the other, which is what separates a pair the structure already explains from a pair it does
    not.
    """

    left: str
    right: str
    shared_commit_count: NonNegativeInt = 0
    left_commit_count: NonNegativeInt = 0
    right_commit_count: NonNegativeInt = 0
    import_reference_count: NonNegativeInt = 0


class RetryPolicyFact(Fact):
    """Describe one retry policy and its failure budget."""


class KernelLaunchFact(Fact):
    """Describe one kernel launch and the execution configuration it sets.

    A launch states four things between its brackets and only the first two are required, so the
    two usually left out are the two worth reading. This arrives from the grammar rather than from
    a text search, because the launch bracket is real syntax that a CUDA parser knows.
    """

    kernel: str = ""
    grid: str = ""
    block: str = ""
    dynamic_shared_bytes: str = ""
    stream: str = ""
    enclosing_function: str = ""
    unit_uses_streams: bool = False


class RouteFact(Fact):
    """Describe every route this repository declares and everything that names one.

    A route has no general detector, so each framework is read by its own small adapter and they
    all produce the same thing. What arrives is the whole set rather than one route at a time,
    because a duplicate, a route nothing reaches, and a path that disagrees with its neighbours are
    all statements about the set.
    """

    frameworks: list[str] = []
    routes: list["Route"] = []


class Route(FrozenFlexModel):
    """Retain one declared route and every literal that names its path."""

    method: str
    path: str
    framework: str
    declared_in: str
    line: PositiveInt = 1
    is_prefix_composed: bool = False
    references: list["RouteReference"] = []


class RouteReference(FrozenFlexModel):
    """Retain one place that names the path of a route as a literal."""

    path: str
    language: str
    line: PositiveInt = 1


class RustSurfaceFact(Fact):
    """Describe what one Rust module borrows, what it pins, and what it copies instead.

    These three arrive together because they are one decision seen from three sides. A lifetime is
    what borrowing costs in the signature, a clone is what not borrowing costs at run time, and a
    `'static` is what pinning costs forever. A rule that read only one of them would push a project
    straight into another.
    """

    annotations: list["LifetimeAnnotation"] = []
    pins: list["StaticLifetime"] = []
    clones: list["CloneCall"] = []


class LifetimeAnnotation(FrozenFlexModel):
    """Retain one declaration that names lifetimes, and every position it names them in.

    The four positions are the ones Rust's elision rules distinguish, and where a lifetime appears
    is something only a parser can see. What the arrangement means is left to the rule.
    """

    owner: str
    kind: Literal["function", "method", "type", "trait", "alias"]
    names: list[str] = []
    line: PositiveInt = 1
    returned: list[str] = []
    receiver: str = ""
    parameters: list[str] = []
    beyond: list[str] = []


class StaticLifetime(FrozenFlexModel):
    """Retain one place that pins something for the whole run of the program.

    A pin in a parameter or a field demands, one in a return supplies, and one in a bound says
    what a type may not borrow. Which of the three it is decides what it costs.
    """

    owner: str = ""
    line: PositiveInt = 1
    position: Literal["demand", "supply", "bound"] = "supply"


class CloneCall(FrozenFlexModel):
    """Retain one copy made where a borrow could not be arranged."""

    receiver: str = ""
    owner: str = ""
    line: PositiveInt = 1
    loop_depth: NonNegativeInt = 0


class RuntimeTypeCheckFact(Fact):
    """Describe one runtime type check and the protocol it requires."""

    checks: list["RuntimeTypeCheck"] = []


class RuntimeTypeCheck(FrozenFlexModel):
    """Retain a concrete isinstance target and guarded operations."""

    concrete_type: str
    guarded_operations: list[str] = []
    can_use_eafp: bool = False


class RunbookFact(Fact):
    """Describe one operational runbook and its exercised procedures."""

    triggers: ChecklistValue = Checklist(root=[])


class SecurityBoundaryFact(Fact):
    """Describe one security boundary and the data crossing it."""

    boundaries: ChecklistValue = Checklist(root=[])


class ServiceObjectiveFact(Fact):
    """Describe one service objective and its measurements."""

    services: ChecklistValue = Checklist(root=[])


class StateFact(Fact):
    """Describe one modeled state and its transitions."""


class StringExpressionFact(Fact):
    """Describe one string-producing expression."""

    expressions: list["StringExpression"] = []


class StringExpression(FrozenFlexModel):
    """Retain lexical and runtime properties for one folded string expression."""

    runtime_value: str
    node: NodeRef | None = None
    literal_fragment_count: PositiveInt = 1
    wraps_single_runtime_line: bool = False
    repeated_literal: str = ""
    repetition_count: NonNegativeInt = 0


class SyntaxFact(Fact):
    """Describe one declaration as both a tree and the source it was written as.

    Every other family answers a question somebody already asked. This one answers the questions
    nobody has asked yet: a rule about how a project spells its local variables, or indents its
    branches, or orders the clauses of a comprehension, needs the code rather than a count of it,
    and until now the only way to reach that was a `NodeRef` some fix happened to leave behind.

    A rule declares this as its subject to say it needs to read code, and pays for the tree by
    asking. Every rule that does not ask never sees it built.
    """

    qualname: str = ""
    kind: str = ""
    source: str = ""
    tree: "SyntaxNode | None" = None


class SyntaxNode(FrozenFlexModel):
    """Retain one node of a declaration's tree, with the source it spans.

    The kinds are language-neutral on purpose. A faithful parse tree makes a rule learn the syntax
    of whichever language produced it, which is exactly what a general rule must not do, so what
    arrives is what a rule asks about: what this binds, what it calls, and what it writes down.
    """

    kind: str
    name: str = ""
    text: str = ""
    span: SourceSpan | None = None
    children: list["SyntaxNode"] = []

    def walk(self) -> Iterator[SyntaxNode]:
        """Yield this node and every node beneath it, in the order the source states them."""
        yield self
        for child in self.children:
            yield from child.walk()

    def of_kind(self, *kinds: str) -> list[SyntaxNode]:
        """Return every node beneath this one of any named kind."""
        return [node for node in self.walk() if node.kind in kinds]

    def names(self, *kinds: str) -> list[str]:
        """Return every name stated beneath this one, narrowed to the kinds asked for."""
        wanted = kinds or None
        return [
            node.name
            for node in self.walk()
            if node.name and (wanted is None or node.kind in wanted)
        ]

    @cached_property
    def depth(self) -> int:
        """Return how deeply this node nests, which is what indentation costs a reader."""
        return 1 + max((child.depth for child in self.children), default=0)


class SymbolReachFact(Fact):
    """Describe how far the references that reach one module's declarations spread."""

    is_test_module: bool = False
    declarations: list["SymbolReach"] = []


class SymbolReach(FrozenFlexModel):
    """Retain one declaration and the spread of every reference that reaches it.

    A declaration nothing reaches, one only its own file reaches, and one a dozen packages reach
    are three different things, and only a repository graph can tell them apart. The counts stay
    primitive so a rule decides what each spread means.
    """

    qualname: str
    kind: Literal["class", "function", "method", "property", "variable", "attribute"]
    visibility: Visibility = Visibility.PUBLIC
    is_module_scope: bool = False
    is_decorated: bool = False
    own_file_references: NonNegativeInt = 0
    other_file_references: NonNegativeInt = 0
    referencing_files: NonNegativeInt = 0
    referencing_directories: NonNegativeInt = 0
    referencing_packages: NonNegativeInt = 0
    call_count: NonNegativeInt = 0
    instantiate_count: NonNegativeInt = 0
    inherit_count: NonNegativeInt = 0
    import_count: NonNegativeInt = 0


class ParameterKind(StrEnum):
    """Name how one parameter binds the argument a caller passes to it.

    Python spells all five, which is why the vocabulary is written from it, and a language that
    binds every argument by position states only the positional-only and variadic forms. What a
    caller must fill and what a caller may name are different promises, so a provider that reports
    only an ordered list of names cannot answer whether two signatures still substitute.
    """

    POSITIONAL_ONLY = auto()
    POSITIONAL_OR_KEYWORD = auto()
    KEYWORD_ONLY = auto()
    VAR_POSITIONAL = auto()
    VAR_KEYWORD = auto()


class ParameterDeclaration(FrozenFlexModel):
    """Retain one parameter exactly as the declaration holding it writes it down."""

    name: str = ""
    kind: ParameterKind = ParameterKind.POSITIONAL_OR_KEYWORD
    has_default: bool = False


class MemberDeclaration(FrozenFlexModel):
    """Retain one member exactly as the class holding it writes it down.

    A callable states its parameters in the order it takes them and data states no parameter list
    at all, so `parameters` being absent is how a reader tells an attribute from a method wearing
    the same name. Nothing here is a verdict, which leaves every question about what two
    declarations mean together to the rule that asks it.
    """

    name: str = ""
    parameters: list[ParameterDeclaration] | None = None
    decorators: list[str] = []
    asynchronous: bool = False
    line: PositiveInt = 1


class OverrideFact(Fact):
    """Describe one inheritance link and what the subclass does with everything it inherits.

    The base of an override usually lives in another file, so finding it means resolving the
    inheritance chain across the whole repository and no syntax reader can do it. Both halves
    arrive together here, and each member is filed under the nearest ancestor that declares it,
    which is the declaration Python itself would reach.

    A link with nothing crossing it still arrives, because inheriting from a sealed class is a
    defect its members say nothing about.
    """

    derived: str = ""
    base: str = ""
    depth: PositiveInt = 1
    derived_decorators: list[str] = []
    base_decorators: list[str] = []
    base_names: list[str] = []
    ancestor_names: list[str] = []
    declared: list[MemberDeclaration] = []
    inherited: list[MemberDeclaration] = []
    initializer_calls: list[str] = []

    @cached_property
    def overrides(self) -> list[tuple[MemberDeclaration, MemberDeclaration]]:
        """Return each member this base declares beside the subclass declaration answering it."""
        answers = {item.name: item for item in self.declared}
        return [(item, answers[item.name]) for item in self.inherited if item.name in answers]

    @cached_property
    def unanswered(self) -> list[MemberDeclaration]:
        """Return every member this base declares that the subclass never writes down again."""
        answered = {item.name for item in self.declared}
        return [item for item in self.inherited if item.name not in answered]


class SymbolFact(Fact):
    """Describe one resolved symbol declaration and its uses."""

    symbols: list["Symbol"] = []
    typing_scopes: list["TypingScope"] = []


class Symbol(FrozenFlexModel):
    """Retain one declaration and its proven value contract."""

    name: str
    scope: Literal["module", "class", "local"]
    is_constant_assignment: bool = False
    returns_boolean: bool = False
    reference: SymbolRef | None = None


class TypingScope(FrozenFlexModel):
    """Retain type declarations and resolved reuse inside one cohesive directory."""

    path: str
    definitions: list[str] = []
    reused_definitions: list[str] = []
    cross_module_import_count: NonNegativeInt = 0
    definitions_outside_preferred_module: list[str] = []


class TelemetryFact(Fact):
    """Describe one telemetry signal and the behavior it observes."""


class TestCaseGroupFact(Fact):
    """Describe one related group of test cases."""

    groups: list["TestCaseGroup"] = []
    loops: list["LiteralTestLoop"] = []


class TestCaseGroup(FrozenFlexModel):
    """Retain sibling tests with the same normalized nonliteral syntax."""

    normalized_syntax: str
    literal_vectors: list[list[str]] = []


class LiteralTestLoop(FrozenFlexModel):
    """Retain one test-owned loop over literal cases."""

    case_count: NonNegativeInt
    owns_assertion: bool


class TestFunctionFact(Fact):
    """Describe one test function and its fixtures and assertions."""

    tests: list["TestFunction"] = []


class TestFunction(FrozenFlexModel):
    """Retain direct syntax and ownership facts for one collected test."""

    name: str
    path: str
    is_collected: bool = True
    is_async: bool = False
    fixture_names: list[str] = []
    requested_fixture_names: list[str] = []
    marks: list[str] = []
    calls: list[CallSite] = []
    module_state_mutation_count: NonNegativeInt = 0
    owned_conditional_count: NonNegativeInt = 0
    owned_statement_count: NonNegativeInt = 0
    parametrized_range_sizes: list[int] = []


class TestStrategyFact(Fact):
    """Describe one test strategy and its risk coverage."""

    failure_scenarios: ChecklistValue = Checklist(root=[])


class TestSuiteFact(Fact):
    """Describe one test suite and its collected execution evidence."""

    quarantined_tests: list["QuarantinedTest"] = []
    strict_mode: bool = False
    strict_controls: dict[str, bool] = {}
    import_mode: str = "prepend"
    anyio_mode: str = ""
    asyncio_mode: str = ""
    is_coverage_configured: bool = False
    is_branch_coverage_enabled: bool = False


class QuarantinedTest(FrozenFlexModel):
    """Retain one quarantined test and its remediation evidence."""

    name: str
    age_days: NonNegativeInt
    owner: str = ""
    has_remediation_evidence: bool = False
    recurred_after_repair: bool = False


class TryBlockFact(Fact):
    """Describe one try statement and its handlers."""

    regions: list["ExceptionRegion"] = []


class ExceptionRegion(FrozenFlexModel):
    """Retain protected setup and executable clause sizes for one try statement."""

    leading_literal_assignment_count: NonNegativeInt = 0
    has_following_raising_operation: bool = False
    clause_statement_counts: list[int] = []
    statement: NodeRef | None = None
    leading_assignments: list[NodeRef] = []


class TypeAnnotationFact(Fact):
    """Describe one resolved type annotation."""

    annotations: list["TypeAnnotation"] = []


class TypeAnnotation(FrozenFlexModel):
    """Retain one resolved annotation and reusable constraint recipe."""

    path: str
    union_members: list[str] = []
    resolved_names: list[str] = []
    constraint_recipe: str = ""
    is_field_specific_metadata: bool = False


class WaiverFact(Fact):
    """Describe one rule waiver and its retained justification."""

    waivers: list["Waiver"] = []


class Waiver(FrozenFlexModel):
    """Retain one suppression and its exact lifecycle metadata."""

    location: str
    age_days: int | None = None
    expires_in_days: int | None = None
    is_overly_broad: bool = False
    metadata: dict[str, str] = {}


# A model that names a later model, or itself, keeps a deferred schema until something first
# validates it. Under free threading two workers can reach that rebuild at the same moment and
# race inside Pydantic, so every fact model resolves its references here, at import, once.
for declaration in list(vars().values()):
    if isinstance(declaration, type) and issubclass(declaration, FrozenFlexModel):
        declaration.model_rebuild()
