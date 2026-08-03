from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    Enum,
    EnumAnalysis,
    EnumFile,
    EnumMember,
    EnumMetadataMap,
    EnumScope,
    Fact,
    LiteralGroupFact,
    SourceSpan,
)
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.python import (
    parallel_enum_metadata,
    redundant_enum_value,
    shared_enum_file_shape,
    shared_enums_module_candidate,
)
from mcmr.table import Table
from mcmr.table import fact_table as in_memory_table

_SPAN = SourceSpan(path="src/enums/status.py")


def fact_table[Family: Fact](first: Family, *rest: Family) -> Table[Fact]:
    """Normalize one or more facts through a single in-memory native table."""
    subjects = (first, *rest)
    return in_memory_table(type(first), subjects)


def query(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Execute one deterministic rule once over a retained table."""
    result = rule.invoke_table(subject, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic enum rule returned a model query")
    return result


def values(result: RuleQuery) -> list[RuleValue]:
    """Return every scalar emitted by one table query in fact order."""
    return [scalar_row_value(row) for row in result.values.collect().iter_rows(named=True)]


def value(
    subject: Table[Fact],
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleValue:
    """Return the one scalar emitted for a single retained fact."""
    answers = values(query(subject, rule, **settings))
    if len(answers) != 1:
        raise ValueError(f"expected one enum value and received {len(answers)}")
    return answers[0]


def test_redundant_enum_value_cases() -> None:
    subject = Enum(
        key="enums",
        span=_SPAN,
        enums=[
            EnumAnalysis(
                name="Status",
                kind="str_enum",
                members=[
                    EnumMember(name="READY", explicit_value="ready", standard_auto_value="ready")
                ],
            )
        ],
    )
    assert value(fact_table(subject), redundant_enum_value) is True
    custom = subject.model_copy(
        update={
            "enums": [subject.enums[0].model_copy(update={"overrides_generate_next_value": True})]
        }
    )
    assert value(fact_table(custom), redundant_enum_value) is False


def test_parallel_enum_metadata_cases() -> None:
    subject = LiteralGroupFact(
        key="metadata",
        span=_SPAN,
        enum_metadata_maps=[
            EnumMetadataMap(
                enum_name="Status",
                keys=["Status.READY", "Status.DONE"],
                values=["Ready", "Done"],
                all_keys_resolve_to_enum=True,
            )
        ],
    )
    assert value(fact_table(subject), parallel_enum_metadata) is True
    unresolved = subject.model_copy(
        update={
            "enum_metadata_maps": [
                subject.enum_metadata_maps[0].model_copy(
                    update={"all_keys_resolve_to_enum": False}
                )
            ]
        }
    )
    assert value(fact_table(unresolved), parallel_enum_metadata) is False


def test_shared_enum_placement_cases() -> None:
    subject = Enum(
        key="enums",
        span=_SPAN,
        scopes=[
            EnumScope(
                destination="src/payments/status.py",
                enum_count=3,
                reused_enum_count=2,
                cross_module_import_count=3,
            ),
            EnumScope(
                destination="src/local/status.py",
                enum_count=2,
                reused_enum_count=1,
                cross_module_import_count=1,
            ),
        ],
        files=[
            EnumFile(
                path="src/enums/status.py",
                top_level_class_count=1,
                enum_class_count=1,
                is_shared_across_unrelated_branches=True,
            ),
            EnumFile(
                path="src/enums/mixed.py",
                top_level_class_count=2,
                enum_class_count=1,
            ),
            EnumFile(
                path="src/enums/__init__.py",
                top_level_class_count=0,
                enum_class_count=0,
                is_package_initializer=True,
            ),
        ],
    )
    table = fact_table(subject)
    assert value(table, shared_enums_module_candidate) == 3
    assert value(table, shared_enum_file_shape) == 1
