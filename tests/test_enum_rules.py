from mcmr.facts import (
    EnumAnalysis,
    EnumFact,
    EnumFile,
    EnumMember,
    EnumMetadataMap,
    EnumScope,
    LiteralGroupFact,
    SourceSpan,
)
from mcmr.rules.python.deterministic.enumerations.r0001 import redundant_enum_value
from mcmr.rules.python.deterministic.enumerations.r0002 import parallel_enum_metadata
from mcmr.rules.python.deterministic.enumerations.r0003 import shared_enums_module_candidate
from mcmr.rules.python.deterministic.enumerations.r0004 import shared_enum_file_shape

SPAN = SourceSpan(path="src/enums/status.py")


def test_redundant_enum_value_cases() -> None:
    subject = EnumFact(
        key="enums",
        span=SPAN,
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
    assert redundant_enum_value(subject)
    custom = subject.model_copy(
        update={
            "enums": [subject.enums[0].model_copy(update={"overrides_generate_next_value": True})]
        }
    )
    assert not redundant_enum_value(custom)


def test_parallel_enum_metadata_cases() -> None:
    subject = LiteralGroupFact(
        key="metadata",
        span=SPAN,
        enum_metadata_maps=[
            EnumMetadataMap(
                enum_name="Status",
                keys=["Status.READY", "Status.DONE"],
                values=["Ready", "Done"],
                all_keys_resolve_to_enum=True,
            )
        ],
    )
    assert parallel_enum_metadata(subject)
    assert not parallel_enum_metadata(
        subject.model_copy(
            update={
                "enum_metadata_maps": [
                    subject.enum_metadata_maps[0].model_copy(
                        update={"all_keys_resolve_to_enum": False}
                    )
                ]
            }
        )
    )


def test_shared_enum_placement_cases() -> None:
    subject = EnumFact(
        key="enums",
        span=SPAN,
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
    assert shared_enums_module_candidate(subject) == 3
    assert shared_enum_file_shape(subject) == 1
