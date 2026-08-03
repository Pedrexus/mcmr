from typing import TYPE_CHECKING, Literal

from patos import FrozenModel
from pydantic import NonNegativeInt

from ...foundation import Fact, SourceSpan, Visibility

if TYPE_CHECKING:
    from .method import MethodAnalysis


class ClassFact(Fact):
    """Describe one class and its resolved members."""

    class AnalysisIdentity(FrozenModel):
        """Retain class identity, source, scope, and visibility."""

        name: str
        path: str
        span: SourceSpan
        is_test: bool = False
        source: str = ""
        scope: Literal["module", "nested"] = "module"
        visibility: Visibility = Visibility.PUBLIC

    class AnalysisDeclaration(AnalysisIdentity):
        """Retain bases, protocol, decoration, method, and state declarations."""

        direct_bases: list[str] = []
        is_protocol: bool = False
        decorators: list[str] = []
        class_keywords: list[str] = []
        methods: list[MethodAnalysis] = []
        has_explicit_registry_name: bool = False
        has_instance_fields: bool = False

    class AnalysisReach(AnalysisDeclaration):
        """Retain fields, inheritance reach, instantiation, and export evidence."""

        field_count: NonNegativeInt = 0
        has_inherited_fields: bool = False
        direct_subclasses: list[str] = []
        descendant_count: NonNegativeInt = 0
        is_instantiated: bool = False
        is_exported: bool = False
        only_cross_module_reference_is_subclass: bool = False

    class AnalysisComposition(AnalysisReach):
        """Retain layering, base overlap, collisions, and model role evidence."""

        is_pass_through_layer: bool = False
        base_is_removable_overlap: bool = False
        has_redundant_direct_base: bool = False
        has_noncooperative_concrete_collision: bool = False
        duplicate_component_alias_count: NonNegativeInt = 0
        is_declarative_model: bool = False
        is_dataclass: bool = False

    class AnalysisModel(AnalysisComposition):
        """Retain behavior, imports, destinations, and Pydantic foundation evidence."""

        has_ordinary_behavior: bool = False
        importing_modules: list[str] = []
        proposed_model_destination: str = ""
        directly_inherits_pydantic_base_model: bool = False
        inherits_approved_model_foundation: bool = False

    class Analysis(AnalysisModel):
        """Retain one class and its closed-world graph properties."""

    class CoupledTypeGroup(FrozenModel):
        """Retain short co-imported role types sharing a name prefix."""

        prefix: str
        span: SourceSpan
        role_suffixes: list[str] = []
        type_count: NonNegativeInt
        maximum_type_lines: NonNegativeInt
        coimporting_module_count: NonNegativeInt

    class ModelFile(FrozenModel):
        """Retain one implementation file below a shared models directory."""

        path: str
        span: SourceSpan
        top_level_class_count: NonNegativeInt
        model_class_count: NonNegativeInt
        is_package_initializer: bool = False

    class AttributeProjection(FrozenModel):
        """Retain matching key and attribute projections from one typed root."""

        root: str
        span: SourceSpan
        attribute_names: list[str] = []
        output_keys: list[str] = []

    classes: list[Analysis] = []
    coupled_groups: list[CoupledTypeGroup] = []
    model_files: list[ModelFile] = []
    projection_groups: list[AttributeProjection] = []
    has_approved_model_foundation_policy: bool = False
