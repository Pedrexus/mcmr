from typing import TYPE_CHECKING

from mcmr.facts import (
    AttributeProjection,
    ClassAnalysis,
    ClassFact,
    CoupledTypeGroup,
    MemberKind,
    MethodAnalysis,
    ModelFile,
    SourceSpan,
    Visibility,
)
from mcmr.rules.general.deterministic.classes.r0002 import class_method_order
from mcmr.rules.general.deterministic.classes.r0006 import nonpublic_top_level_class_count
from mcmr.rules.python.deterministic.classes.r0001 import explicit_registry_name
from mcmr.rules.python.deterministic.classes.r0005 import coupled_nested_type_candidate
from mcmr.rules.python.deterministic.classes.r0007 import utility_namespace_class_count
from mcmr.rules.python.deterministic.classes.r0008 import (
    staticmethod_calling_classmethod_count,
)
from mcmr.rules.python.deterministic.classes.r0009 import (
    artificial_single_subclass_base_count,
)
from mcmr.rules.python.deterministic.classes.r0010 import (
    pass_through_inheritance_layer_count,
)
from mcmr.rules.python.deterministic.classes.r0011 import (
    hazardous_multiple_inheritance_mro_count,
)
from mcmr.rules.python.deterministic.classes.r0013 import (
    duplicate_component_attribute_alias_count,
)
from mcmr.rules.python.deterministic.models.r0002 import shared_model_file_shape
from mcmr.rules.python.deterministic.models.r0003 import shared_model_placement
from mcmr.rules.python.deterministic.models.r0004 import approved_model_foundation
from mcmr.rules.python.deterministic.models.r0005 import manual_model_attribute_projection_count

if TYPE_CHECKING:
    from tests.conftest import Declared

SPAN = SourceSpan(path="src/models/policy.py")


def classes(*declared: ClassAnalysis, **shapes: Declared) -> ClassFact:
    """Return one class fact holding the given analyses and the grouped shapes read beside them."""
    return ClassFact.model_validate(
        {"key": "classes", "span": SPAN, "classes": list(declared)} | shapes
    )


def test_registry_name_and_method_order_cases() -> None:
    registry = ClassAnalysis(
        name="HarnessBackend",
        path="src/backends.py",
        direct_bases=["patos.Registry", "Backend"],
        has_explicit_registry_name=True,
        methods=[
            MethodAnalysis(name="run"),
            MethodAnalysis(name="__init__", is_protocol_name=True),
        ],
    )
    subject = classes(registry)
    assert explicit_registry_name(subject)
    assert class_method_order(subject).value == 1
    ordered = registry.model_copy(update={"methods": list(reversed(registry.methods))})
    assert class_method_order(classes(ordered)).value == 0


def test_coupled_and_private_class_cases() -> None:
    subject = classes(
        ClassAnalysis(name="_Private", path="src/types.py", visibility=Visibility.INTERNAL),
        ClassAnalysis(
            name="_Nested",
            path="src/types.py",
            scope="nested",
            visibility=Visibility.INTERNAL,
        ),
        coupled_groups=[
            CoupledTypeGroup(
                prefix="Message",
                role_suffixes=["Content", "Kind"],
                type_count=2,
                maximum_type_lines=20,
                coimporting_module_count=2,
            )
        ],
    )
    assert coupled_nested_type_candidate(subject) == 1
    assert nonpublic_top_level_class_count(subject) == 1


def test_class_body_shape_cases() -> None:
    """The members of one class say whether it is a type at all and what it repeats.

    A class holding only static behavior is a namespace, a static method reaching for its own
    classmethod wants the binding it refused, and the same component aliased under several
    attribute names is one declaration written many times. Instance fields answer the first of
    those, so a utility gaining one stops counting.
    """
    utility = ClassAnalysis(
        name="Utilities",
        path="src/utilities.py",
        methods=[
            MethodAnalysis(
                name="build",
                kind=MemberKind.STATIC_METHOD,
                decorators=["staticmethod"],
                owner_qualified_calls=["Utilities.from_config"],
            ),
            MethodAnalysis(
                name="from_config",
                kind=MemberKind.CLASS_METHOD,
                decorators=["classmethod"],
            ),
        ],
    )
    subject = classes(utility)
    assert utility_namespace_class_count(subject) == 1
    assert staticmethod_calling_classmethod_count(subject) == 1
    assert (
        utility_namespace_class_count(
            classes(utility.model_copy(update={"has_instance_fields": True}))
        )
        == 0
    )

    aliased = classes(
        ClassAnalysis(name="Analyzer", path="src/analyzer.py", duplicate_component_alias_count=3)
    )
    assert duplicate_component_attribute_alias_count(aliased) == 3


def test_inheritance_graph_cases() -> None:
    removable = ClassAnalysis(
        name="Base",
        path="src/base.py",
        direct_bases=["object"],
        direct_subclasses=["OnlyChild"],
        descendant_count=1,
        only_cross_module_reference_is_subclass=True,
    )
    pass_through = ClassAnalysis(
        name="AliasLayer",
        path="src/layer.py",
        direct_bases=["Base"],
        is_pass_through_layer=True,
    )
    overlapping = pass_through.model_copy(
        update={"name": "Overlap", "base_is_removable_overlap": True}
    )
    hazardous = ClassAnalysis(
        name="Diamond",
        path="src/diamond.py",
        direct_bases=["Left", "Right"],
        has_noncooperative_concrete_collision=True,
    )
    subject = classes(removable, pass_through, overlapping, hazardous)
    assert artificial_single_subclass_base_count(subject) == 1
    assert pass_through_inheritance_layer_count(subject) == 1
    assert hazardous_multiple_inheritance_mro_count(subject) == 1


def test_model_declaration_cases() -> None:
    """A declarative model is read for where it lives, what founds it, and what it projects out.

    The file shape and the placement follow the destination the model proposes, the foundation
    holds only while the project states one and the model has not inherited it, and a projection
    counts once it restates enough attributes to be the model's own dump.
    """
    model = ClassAnalysis(
        name="Policy",
        path="src/policy.py",
        is_declarative_model=True,
        importing_modules=["src.cli", "src.engine"],
        proposed_model_destination="src/models/policy.py",
        directly_inherits_pydantic_base_model=True,
    )
    subject = classes(
        model,
        model_files=[
            ModelFile(path="src/models/policy.py", top_level_class_count=1, model_class_count=1),
            ModelFile(path="src/models/mixed.py", top_level_class_count=2, model_class_count=1),
        ],
        has_approved_model_foundation_policy=True,
    )
    assert shared_model_file_shape(subject) == 1
    assert shared_model_placement(subject).value == 1
    assert approved_model_foundation(subject) == 1
    approved = subject.model_copy(
        update={"classes": [model.model_copy(update={"inherits_approved_model_foundation": True})]}
    )
    assert approved_model_foundation(approved) == 0
    assert (
        approved_model_foundation(
            subject.model_copy(update={"has_approved_model_foundation_policy": False})
        )
        == 0
    )

    projected = classes(
        projection_groups=[
            AttributeProjection(
                root="definition",
                attribute_names=["id", "summary", "status", "source_hash"],
                output_keys=["id", "summary", "status", "source-hash"],
            ),
            AttributeProjection(
                root="small",
                attribute_names=["id", "status"],
                output_keys=["id", "status"],
            ),
        ]
    )
    assert manual_model_attribute_projection_count(projected) == 1
    assert manual_model_attribute_projection_count(projected, minimum_attributes=5) == 0
