from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    Fact,
    FunctionFact,
    PydanticFieldAnalysis,
    PydanticModelAnalysis,
    PydanticModelFact,
    PydanticValidator,
    SourceSpan,
)
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.python import (
    constructor_model_candidate,
    declarative_field_constraint_candidate,
    imperative_model_input_validation,
    implicit_arbitrary_type_model,
    optional_variant_discriminated_union_candidate,
    redundant_model_validate,
    single_field_model_validator,
    variadic_tuple_model_field,
)
from mcmr.table import AnalysisSession, FunctionRelation, Table

from ..support import retained_query

if TYPE_CHECKING:
    from pathlib import Path

_SPAN = SourceSpan(path="src/models.py")


def scalar(query: RuleQuery) -> RuleValue:
    """Return the populated scalar from one retained fact row."""
    return scalar_frame_value(query.values.collect())


def native_query(
    table: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one specialized Pydantic rule once over a repository table."""
    result = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic Pydantic rule returned a model query")
    return result


def function_value(table: Table[Fact], query: RuleQuery, name: str) -> RuleValue:
    """Return one named function's scalar from a repository-wide query."""
    functions = table.frame(FunctionRelation.FUNCTIONS)
    fact_id = functions.filter(functions["name"] == name).item(0, "fact_id")
    values = query.values.collect()
    return scalar_frame_value(values.filter(values["fact_id"] == fact_id))


def test_validator_structure_cases() -> None:
    subject = PydanticModelFact(
        key="models",
        span=_SPAN,
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
    assert scalar(retained_query(subject, single_field_model_validator)) == 1
    assert scalar(retained_query(subject, declarative_field_constraint_candidate)) == 2
    assert scalar(retained_query(subject, optional_variant_discriminated_union_candidate)) == 1
    assert (
        scalar(
            retained_query(
                subject,
                optional_variant_discriminated_union_candidate,
                minimum_variants=4,
            )
        )
        == 0
    )


def test_imperative_factory_validation_cases(tmp_path: Path) -> None:
    (tmp_path / "models.py").write_text(
        """from pydantic import BaseModel, field_validator

class Order(BaseModel):
    rows: list[dict]

    @classmethod
    def from_table(cls, rows):
        if not isinstance(rows, list):
            raise ValueError(rows)
        return cls(rows=rows)

    @field_validator('rows')
    @classmethod
    def check(cls, value):
        return value
""",
        encoding="utf-8",
    )
    table = cast(
        "Table[Fact]",
        AnalysisSession(
            tmp_path,
            suffixes=(".py",),
            typed_families=(FunctionFact.__name__,),
        ).function_tables(),
    )
    query = native_query(table, imperative_model_input_validation)

    assert function_value(table, query, "from_table") == 1
    assert function_value(table, query, "check") == 0


def test_known_mapping_model_validate_cases(tmp_path: Path) -> None:
    (tmp_path / "models.py").write_text(
        """from pydantic import BaseModel

class Policy(BaseModel):
    name: str

def build(name, payload):
    known = Policy.model_validate({'name': name})
    unknown = Policy.model_validate(payload)
    return known, unknown
""",
        encoding="utf-8",
    )
    table = cast(
        "Table[Fact]",
        AnalysisSession(
            tmp_path,
            suffixes=(".py",),
            typed_families=("CallFact",),
        ).call_tables(),
    )

    assert scalar(native_query(table, redundant_model_validate)) == 1


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
    subject = PydanticModelFact(key="models", span=_SPAN, models=[candidate])
    assert scalar(retained_query(subject, constructor_model_candidate)) == 1
    assert (
        scalar(
            retained_query(
                subject.model_copy(
                    update={"models": [candidate.model_copy(update={"validation_count": 0})]}
                ),
                constructor_model_candidate,
            )
        )
        == 0
    )


def test_variadic_tuple_model_field_cases() -> None:
    tuple_span = _SPAN.model_copy(update={"start_line": 8, "end_line": 8})
    model = PydanticModelAnalysis(
        name="Profile",
        is_pydantic_model=True,
        fields=[
            PydanticFieldAnalysis(
                name="tags",
                annotation="tuple[str, ...]",
                span=tuple_span,
                contains_variadic_tuple=True,
            ),
            PydanticFieldAnalysis(
                name="point",
                annotation="tuple[int, int]",
                span=_SPAN,
            ),
        ],
    )
    plain = model.model_copy(update={"name": "Plain", "is_pydantic_model": False})
    subject = PydanticModelFact(key="models", span=_SPAN, models=[model, plain])
    report = retained_query(subject, variadic_tuple_model_field)
    assert report.findings is not None
    findings = report.findings.rows.collect()
    assert (
        scalar(report),
        findings.height,
        findings.item(0, "path"),
        findings.item(0, "start_line"),
        findings.item(0, "end_line"),
        "`Profile.tags` uses `tuple[str, ...]`" in findings.item(0, "message"),
    ) == (1, 1, tuple_span.path, tuple_span.start_line, tuple_span.end_line, True)


def test_implicit_arbitrary_type_model_cases() -> None:
    flexible_span = _SPAN.model_copy(update={"start_line": 4, "end_line": 4})
    flexible = PydanticModelAnalysis(
        name="Catalog",
        is_pydantic_model=True,
        uses_flexible_model=True,
        flexible_base_span=flexible_span,
    )
    subject = PydanticModelFact(
        key="models",
        span=_SPAN,
        models=[flexible, PydanticModelAnalysis(name="Policy", is_pydantic_model=True)],
    )

    report = retained_query(subject, implicit_arbitrary_type_model)

    assert scalar(report) == 1
    assert report.findings is not None
    finding = report.findings.rows.collect().row(0, named=True)
    assert finding["path"] == flexible_span.path
    assert finding["start_line"] == flexible_span.start_line
    assert "`Catalog` permits arbitrary field types" in finding["message"]
