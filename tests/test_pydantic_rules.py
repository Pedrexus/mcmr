from mcmr.facts import (
    CallFact,
    CallSite,
    Expression,
    FunctionFact,
    LiteralKind,
    PydanticModelAnalysis,
    PydanticModelFact,
    PydanticValidator,
    SourceSpan,
)
from mcmr.rules.python.deterministic.pydantic.r0001 import single_field_model_validator
from mcmr.rules.python.deterministic.pydantic.r0002 import declarative_field_constraint_candidate
from mcmr.rules.python.deterministic.pydantic.r0003 import imperative_model_input_validation
from mcmr.rules.python.deterministic.pydantic.r0004 import redundant_model_validate
from mcmr.rules.python.deterministic.pydantic.r0005 import (
    optional_variant_discriminated_union_candidate,
)
from mcmr.rules.python.deterministic.pydantic.r0006 import constructor_model_candidate

SPAN = SourceSpan(path="src/models.py")


def test_validator_structure_cases() -> None:
    subject = PydanticModelFact(
        key="models",
        span=SPAN,
        models=[
            PydanticModelAnalysis(
                name="Policy",
                validators=[
                    PydanticValidator(kind="model_after", fields_read=["name"]),
                    PydanticValidator(
                        kind="model_after",
                        fields_read=["minimum", "maximum"],
                    ),
                    PydanticValidator(
                        kind="field",
                        fields_read=["name"],
                        declarative_constraint_count=2,
                    ),
                    PydanticValidator(
                        kind="model_after",
                        fields_read=["expected", "minimum", "accepted"],
                        proves_disjoint_optional_variants=True,
                        variant_count=3,
                    ),
                ],
            )
        ],
    )
    assert single_field_model_validator(subject) == 1
    assert declarative_field_constraint_candidate(subject) == 2
    assert optional_variant_discriminated_union_candidate(subject) == 1
    assert optional_variant_discriminated_union_candidate(subject, minimum_variants=4) == 0


def test_imperative_factory_validation_cases() -> None:
    subject = FunctionFact(
        key="factory",
        span=SPAN,
        name="from_table",
        is_model_method=True,
        checks_raw_input_type=True,
        raises_validation_exception=True,
        constructs_owner_model=True,
    )
    assert imperative_model_input_validation(subject) == 1
    assert (
        imperative_model_input_validation(
            subject.model_copy(update={"is_pydantic_validator": True})
        )
        == 0
    )


def test_known_mapping_model_validate_cases() -> None:
    subject = CallFact(
        key="calls",
        span=SPAN,
        calls=[
            CallSite(
                qualified_name="Policy.model_validate",
                path="src/models.py",
                arguments=[Expression(text="{'name': name}", literal_kind=LiteralKind.MAPPING)],
            ),
            CallSite(
                qualified_name="Policy.model_validate",
                path="src/models.py",
                arguments=[Expression(text="payload")],
            ),
        ],
    )
    assert redundant_model_validate(subject) == 1


def test_constructor_model_cases() -> None:
    candidate = PydanticModelAnalysis(
        name="Configuration",
        is_undecorated_plain_class=True,
        synchronous_init_count=1,
        fixed_parameter_count=4,
        stored_parameter_count=4,
        validation_count=1,
        default_count=1,
        has_only_data_identity_methods=True,
    )
    subject = PydanticModelFact(key="models", span=SPAN, models=[candidate])
    assert constructor_model_candidate(subject) == 1
    assert (
        constructor_model_candidate(
            subject.model_copy(
                update={"models": [candidate.model_copy(update={"validation_count": 0})]}
            )
        )
        == 0
    )
