import typing
from collections import abc

import pydantic
from patos import FrozenModel

from ..domain.primitives import NonEmptyStr
from ..versioning import CoChangedPair, FileHistory, HistoryChange
from .foundation import (
    DetectableCloneTokenCount,
    Evidence,
    Fact,
    MemberKind,
    NodeRef,
    Ratio,
    ReceiverKind,
    Relation,
    SourceSpan,
    SymbolRef,
    Visibility,
)
from .languages import (
    CloneCall,
    KernelLaunchFact,
    LifetimeAnnotation,
    LiteralStringExpression,
    RepeatedStringExpression,
    Route,
    RouteFact,
    RouteReference,
    RunbookFact,
    RunbookTrigger,
    RuntimeTypeCheck,
    RuntimeTypeCheckFact,
    RustSurfaceFact,
    SecurityBoundary,
    SecurityBoundaryFact,
    ServiceObjective,
    ServiceObjectiveFact,
    StaticLifetime,
    StringExpressionFact,
    SyntaxFact,
)
from .program.exceptions.fact import ExceptionFact
from .program.exceptions.usage import ExceptionUsage
from .program.features.fact import FeatureFlagFact
from .program.features.flag import FeatureFlag
from .program.functions.fact import FunctionFact
from .program.functions.types import ControlKind
from .program.interop.fact import InteropFact
from .program.interop.mechanism import InteropMechanism
from .program.interop.reference import InteropReference
from .program.lineage.edge import LineageEdge
from .program.lineage.fact import LineageEdgeFact
from .program.literals.enum import EnumMetadataMap
from .program.literals.fact import LiteralGroupFact
from .program.literals.string import StringLiteralGroup
from .program.methods.fact import MethodGroupFact
from .program.methods.group import MethodCloneGroup
from .program.module_surface import ErasableConstruct, EscapeHatch, ModuleSurfaceFact
from .program.module_surface.types import ModuleSurfaceTypes as _ModuleSurfaceTypes
from .program.modules import (
    ConstantPlacement,
    ModuleCoupling,
    ModuleCouplingFact,
    ModuleFact,
)
from .project.configuration.assignment import ConfigurationAssignment
from .project.configuration.fact import ProjectConfigurationFact
from .project.configuration.python import PythonTargetConfiguration
from .project.history.fact import RepositoryHistoryFact
from .project.parameters.fact import ParameterFact
from .project.parameters.use import ParameterUse
from .project.performance.budget import PerformanceBudget
from .project.performance.fact import PerformanceDecisionFact
from .project.prose.fact import ProseSegmentFact
from .project.prose.section import ProseSection
from .project.pydantic import (
    PydanticFieldAnalysis,
    PydanticModelAnalysis,
    PydanticModelFact,
    PydanticValidator,
)
from .project.queries.fact import QueryFact
from .project.queries.operation import QueryOperation
from .project.risks.fact import OperationalRiskFact
from .project.risks.risk import OperationalRisk as OperationalRisk
from .structure.alerts.definition import AlertDefinition
from .structure.alerts.fact import AlertFact
from .structure.architecture.characteristic import ArchitectureCharacteristic
from .structure.architecture.fact import ArchitectureCharacteristicFact
from .structure.attributes.access import AttributeAccess
from .structure.attributes.fact import AttributeAccessFact
from .structure.authorship.fact import AuthorshipSignalFact
from .structure.authorship.match import AuthorshipMatch
from .structure.automation.fact import AutomationTaskFact
from .structure.automation.task import AutomationTask
from .structure.branches import BranchFact, ConditionalArm, ConditionalChain
from .structure.calls.expression import Expression
from .structure.calls.fact import CallFact
from .structure.calls.mapping import MappingEntry
from .structure.changes import ChangeApproval, ChangeFact, ChangeRecord
from .structure.ci import CICheck, CICheckFact, CIConfigurationFact, CIWorkflow
from .structure.classes.fact import ClassFact
from .structure.classes.method import MethodAnalysis
from .structure.clones.fact import CloneGroupFact
from .structure.clones.fragment import CloneFragment
from .structure.comments.fact import CommentFact
from .structure.comments.group import CommentGroup
from .structure.comprehensions.candidate import SetLoopCandidate
from .structure.comprehensions.fact import ComprehensionFact
from .structure.data import (
    DataAsset,
    DataAssetFact,
    DataAssetReference,
    DataAssetReferenceFact,
    DataChange,
    DataChangeFact,
    DataField,
    DataFieldReference,
    DataFieldReferenceFact,
)
from .structure.dependencies import (
    DependencyComponentFact,
    DependencyEdge,
    DependencyFact,
    DependencyProjectState,
    DependencyRecord,
    DependencyReleaseState,
    DependencyRepositoryState,
)
from .structure.deployment.fact import DeploymentFact
from .structure.directories.fact import DirectoryFact
from .structure.enumeration import Enum, EnumAnalysis, EnumFile, EnumMember, EnumScope
from .structure.imports.fact import ImportBindingFact
from .structure.local_collections.fact import CollectionFact
from .structure.local_collections.local import LocalCollection
from .structure.local_collections.pairs import PairSequence
from .symbols.declarations.kind import ParameterKind
from .symbols.declarations.member import MemberDeclaration
from .symbols.declarations.parameter import ParameterDeclaration
from .symbols.exports import ExportBypass, ExportFact, PublicExport
from .symbols.identity.fact import SymbolFact
from .symbols.identity.symbol import Symbol
from .symbols.overrides.fact import OverrideFact
from .symbols.reach.declaration import SymbolReach
from .symbols.reach.fact import SymbolReachFact
from .symbols.syntax.node import SyntaxNode
from .symbols.typing.definition import TypingDefinition
from .symbols.typing.reuse import TypingReuse
from .symbols.typing.scope import TypingScope
from .testing.annotations.annotation import TypeAnnotation
from .testing.annotations.fact import TypeAnnotationFact
from .testing.cases.fact import TestCaseGroupFact
from .testing.cases.group import TestCaseGroup
from .testing.cases.loop import LiteralTestLoop
from .testing.exceptions.fact import TryBlockFact
from .testing.exceptions.handler import ExceptionHandler
from .testing.exceptions.region import ExceptionRegion
from .testing.functions.call import TestCallSite
from .testing.functions.fact import TestFunctionFact
from .testing.functions.function import TestFunction
from .testing.strategy.fact import TestStrategyFact
from .testing.strategy.failure import FailureScenario as FailureScenario
from .testing.suite.fact import TestSuiteFact
from .testing.suite.quarantined import QuarantinedTest
from .testing.waivers.fact import WaiverFact
from .testing.waivers.waiver import Waiver

_declarations = list(globals().values())
_namespace = dict(globals()) | {
    "Annotated": typing.Annotated,
    "Literal": typing.Literal,
    "Mapping": abc.Mapping,
    "ModuleSurfaceTypes": _ModuleSurfaceTypes,
    "NonEmptyStr": NonEmptyStr,
    "NonNegativeFloat": pydantic.NonNegativeFloat,
    "NonNegativeInt": pydantic.NonNegativeInt,
    "PositiveInt": pydantic.PositiveInt,
    "SecurityBoundary": SecurityBoundary,
    "Self": typing.Self,
    "Sequence": abc.Sequence,
}
for _declaration in _declarations:
    if isinstance(_declaration, type) and issubclass(_declaration, FrozenModel):
        _declaration.model_rebuild(_types_namespace=_namespace)

__all__ = [
    "AlertDefinition",
    "AlertFact",
    "ArchitectureCharacteristic",
    "ArchitectureCharacteristicFact",
    "AttributeAccess",
    "AttributeAccessFact",
    "AuthorshipMatch",
    "AuthorshipSignalFact",
    "AutomationTask",
    "AutomationTaskFact",
    "BranchFact",
    "CICheck",
    "CICheckFact",
    "CIConfigurationFact",
    "CIWorkflow",
    "CallFact",
    "ChangeApproval",
    "ChangeFact",
    "ChangeRecord",
    "ClassFact",
    "CloneCall",
    "CloneFragment",
    "CloneGroupFact",
    "CollectionFact",
    "CommentFact",
    "CommentGroup",
    "ComprehensionFact",
    "ConditionalArm",
    "ConditionalChain",
    "ConfigurationAssignment",
    "ConstantPlacement",
    "ControlKind",
    "CoChangedPair",
    "DataAsset",
    "DataAssetFact",
    "DataAssetReference",
    "DataAssetReferenceFact",
    "DataChange",
    "DataChangeFact",
    "DataField",
    "DataFieldReference",
    "DataFieldReferenceFact",
    "DependencyComponentFact",
    "DependencyEdge",
    "DependencyFact",
    "DependencyProjectState",
    "DependencyRecord",
    "DependencyReleaseState",
    "DependencyRepositoryState",
    "DeploymentFact",
    "DetectableCloneTokenCount",
    "DirectoryFact",
    "EnumAnalysis",
    "Enum",
    "EnumFile",
    "EnumMember",
    "EnumMetadataMap",
    "EnumScope",
    "ErasableConstruct",
    "EscapeHatch",
    "Evidence",
    "ExportBypass",
    "ExportFact",
    "ExceptionFact",
    "ExceptionRegion",
    "ExceptionHandler",
    "ExceptionUsage",
    "Expression",
    "Fact",
    "FeatureFlag",
    "FeatureFlagFact",
    "FileHistory",
    "FunctionFact",
    "HistoryChange",
    "ImportBindingFact",
    "InteropFact",
    "InteropMechanism",
    "InteropReference",
    "KernelLaunchFact",
    "LifetimeAnnotation",
    "LineageEdge",
    "LineageEdgeFact",
    "LiteralGroupFact",
    "LiteralStringExpression",
    "LiteralTestLoop",
    "LocalCollection",
    "MappingEntry",
    "MemberDeclaration",
    "MemberKind",
    "MethodAnalysis",
    "MethodCloneGroup",
    "MethodGroupFact",
    "ModuleCoupling",
    "ModuleCouplingFact",
    "ModuleFact",
    "ModuleSurfaceFact",
    "NodeRef",
    "OperationalRiskFact",
    "OverrideFact",
    "PairSequence",
    "ParameterDeclaration",
    "ParameterFact",
    "ParameterKind",
    "ParameterUse",
    "PerformanceBudget",
    "PerformanceDecisionFact",
    "ProjectConfigurationFact",
    "PublicExport",
    "ProseSection",
    "ProseSegmentFact",
    "PydanticFieldAnalysis",
    "PydanticModelAnalysis",
    "PydanticModelFact",
    "PydanticValidator",
    "PythonTargetConfiguration",
    "QuarantinedTest",
    "QueryFact",
    "QueryOperation",
    "Ratio",
    "ReceiverKind",
    "Relation",
    "RepeatedStringExpression",
    "RepositoryHistoryFact",
    "Route",
    "RouteFact",
    "RouteReference",
    "RunbookFact",
    "RunbookTrigger",
    "RuntimeTypeCheck",
    "RuntimeTypeCheckFact",
    "RustSurfaceFact",
    "SecurityBoundaryFact",
    "ServiceObjective",
    "ServiceObjectiveFact",
    "SetLoopCandidate",
    "SourceSpan",
    "StaticLifetime",
    "StringExpressionFact",
    "StringLiteralGroup",
    "Symbol",
    "SymbolFact",
    "SymbolReach",
    "SymbolReachFact",
    "SymbolRef",
    "SyntaxFact",
    "SyntaxNode",
    "TestCallSite",
    "TestCaseGroup",
    "TestCaseGroupFact",
    "TestFunction",
    "TestFunctionFact",
    "TestStrategyFact",
    "TestSuiteFact",
    "TryBlockFact",
    "TypeAnnotation",
    "TypeAnnotationFact",
    "TypingDefinition",
    "TypingReuse",
    "TypingScope",
    "Visibility",
    "Waiver",
    "WaiverFact",
]
