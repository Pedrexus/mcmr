from .foundation import Fact

_native_names = {
    "AttributeAccessFact",
    "AutomationTaskFact",
    "BranchFact",
    "CallFact",
    "ClassFact",
    "CloneGroupFact",
    "CollectionFact",
    "CommentFact",
    "ComprehensionFact",
    "DependencyComponentFact",
    "DirectoryFact",
    "Enum",
    "ExceptionFact",
    "ExportFact",
    "FunctionFact",
    "ImportBindingFact",
    "InteropFact",
    "KernelLaunchFact",
    "LiteralGroupFact",
    "MethodGroupFact",
    "ModuleCouplingFact",
    "ModuleFact",
    "ModuleSurfaceFact",
    "OverrideFact",
    "ParameterFact",
    "ProjectConfigurationFact",
    "ProseSegmentFact",
    "PydanticModelFact",
    "QueryFact",
    "RepositoryHistoryFact",
    "RouteFact",
    "RuntimeTypeCheckFact",
    "RustSurfaceFact",
    "StringExpressionFact",
    "SymbolFact",
    "SymbolReachFact",
    "SyntaxFact",
    "TestCaseGroupFact",
    "TestFunctionFact",
    "TestSuiteFact",
    "TryBlockFact",
    "TypeAnnotationFact",
    "WaiverFact",
}


def buildable() -> dict[str, type[Fact]]:
    """Return every fact family the analysis kernel knows how to build, by name."""
    pending = [Fact]
    descendants: set[type[Fact]] = set()
    while pending:
        pending.extend(pending.pop().__subclasses__())
        descendants.update(pending)
    families = {
        family.__name__: family for family in descendants if family.__name__ in _native_names
    }
    if missing := _native_names - families.keys():
        raise RuntimeError(f"native fact declarations are missing {', '.join(sorted(missing))}")
    return families
