from typing import TYPE_CHECKING

from ....facts import (
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
    Enum,
    ExceptionFact,
    ExportFact,
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

if TYPE_CHECKING:
    from ....domain.contracts import RuleContract

_FAMILIES = (
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
    Enum,
    ExportFact,
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


def buildable() -> dict[str, type[Fact]]:
    """Return every fact family the analysis kernel knows how to build, by name."""
    return {fact.__name__: fact for fact in _FAMILIES}


def requested_fact(rule: RuleContract) -> type[Fact]:
    """Return the primary fact family whose identities one rule answers for."""
    return rule.primary_family


def requested_facts(rule: RuleContract) -> set[type[Fact]]:
    """Return every fact family declared through a rule's table parameters."""
    return {family for _, family in rule.tables}
