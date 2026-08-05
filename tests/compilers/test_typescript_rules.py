from typing import cast

import polars as pl
from patos import FrozenModel, Runtime

from mcmr.domain.contracts import RuleContract, RuleValue
from mcmr.facts import ErasableConstruct, EscapeHatch, ModuleSurfaceFact, SourceSpan
from mcmr.plugins import fact_table
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.typescript import (
    escape_hatch_density,
    non_erasable_construct,
    relative_import_depth,
    star_reexport_surface,
)

_SPAN = SourceSpan(path="src/index.ts")


class QueryAnswer(FrozenModel):
    """Expose one scalar and its ordered relational findings."""

    value: RuleValue
    findings: Runtime[pl.DataFrame]


def surface(
    *,
    star_reexports: list[str] | None = None,
    named_reexport_count: int = 0,
    deepest_relative_import: int = 0,
    deepest_relative_specifier: str = "",
    physical_line_count: int = 0,
    erasable_violations: list[ErasableConstruct] | None = None,
    escape_hatches: list[EscapeHatch] | None = None,
) -> ModuleSurfaceFact:
    """Build the surface one TypeScript module publishes."""
    return ModuleSurfaceFact(
        key="surface:index",
        span=_SPAN,
        language="typescript",
        star_reexports=[] if star_reexports is None else star_reexports,
        named_reexport_count=named_reexport_count,
        deepest_relative_import=deepest_relative_import,
        deepest_relative_specifier=deepest_relative_specifier,
        physical_line_count=physical_line_count,
        erasable_violations=[] if erasable_violations is None else erasable_violations,
        escape_hatches=[] if escape_hatches is None else escape_hatches,
    )


def answer(rule: RuleContract, subject: ModuleSurfaceFact) -> QueryAnswer:
    """Run one TypeScript rule once over one in-memory module table."""
    table = fact_table(ModuleSurfaceFact, [subject])
    result = rule.invoke_table(table, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic TypeScript rule returned a model query")
    value = scalar_frame_value(result.values.collect())
    findings = pl.DataFrame() if result.findings is None else result.findings.rows.collect()
    return QueryAnswer(value=value, findings=findings)


def measurements(answered: QueryAnswer, index: int) -> dict[str, float]:
    """Return one finding's measurement names and values."""
    names = cast("list[str]", answered.findings.get_column("measurement_names").to_list()[index])
    values = cast(
        "list[float]", answered.findings.get_column("measurement_values").to_list()[index]
    )
    return dict(zip(names, values, strict=True))


def test_a_wholesale_reexport_is_counted_and_names_the_module() -> None:
    subject = surface(
        star_reexports=["./UserService", "./internal/userValidation"],
        named_reexport_count=9,
    )
    answered = answer(star_reexport_surface, subject)

    assert answered.value == 2
    assert answer(star_reexport_surface, surface(named_reexport_count=9)).value == 0
    assert answered.findings.item(1, "message") == (
        "`src/index.ts` re-exports everything `./internal/userValidation` happens to export, so a "
        "helper added there joins this module's contract unreviewed"
    )
    assert answered.findings.item(1, "path") == "src/index.ts"
    assert answered.findings.item(1, "start_line") == 1
    assert measurements(answered, 1) == {
        "wholesale re-exports": 2.0,
        "named re-exports beside them": 9.0,
    }


def test_the_deepest_climb_is_what_a_module_reports() -> None:
    answered = answer(
        relative_import_depth,
        surface(deepest_relative_import=3, deepest_relative_specifier="../../../models/user"),
    )

    assert answered.value == 3
    assert answered.findings.item(0, "message") == (
        "`src/index.ts` imports through `../../../models/user`, which climbs 3 directories out of "
        "its own"
    )
    assert measurements(answered, 0) == {"directories it climbs": 3.0}
    empty = answer(relative_import_depth, surface())
    assert empty.value == 0
    assert empty.findings.is_empty()


def test_every_construct_that_survives_stripping_is_counted() -> None:
    answered = answer(
        non_erasable_construct,
        surface(
            physical_line_count=40,
            erasable_violations=[
                ErasableConstruct(kind="enum", name="Status", line=3),
                ErasableConstruct(kind="parameter_property", name="limit", line=9),
            ],
        ),
    )

    assert answered.value == 2
    assert answered.findings.item(1, "message") == (
        "`limit` is a parameter property, which generates JavaScript rather than disappearing "
        "with the types"
    )
    assert answered.findings.item(1, "start_line") == 9
    assert measurements(answered, 1) == {
        "constructs stripping cannot erase": 2.0,
        "lines in the module": 40.0,
    }
    assert answer(non_erasable_construct, surface()).value == 0


def test_escape_hatch_density_is_measured_against_module_lines() -> None:
    answered = answer(
        escape_hatch_density,
        surface(
            physical_line_count=200,
            escape_hatches=[EscapeHatch(kind="assertion", line=index) for index in range(1, 11)],
        ),
    )

    assert answered.value == 5.0
    assert answered.findings.item(0, "message") == (
        "`src/index.ts` states a type assertion here, one of 10 places it steps around its own "
        "types"
    )
    assert measurements(answered, 0) == {
        "hatches in the module": 10.0,
        "lines in the module": 200.0,
        "share of the module": 5.0,
    }
    assert answer(escape_hatch_density, surface(physical_line_count=0)).value == 0.0


def test_every_kind_of_hatch_is_named_in_source_words() -> None:
    answered = answer(
        escape_hatch_density,
        surface(
            physical_line_count=8,
            escape_hatches=[
                EscapeHatch(kind="non_null", line=2),
                EscapeHatch(kind="any", line=4),
                EscapeHatch(kind="ignore_comment", line=6),
            ],
        ),
    )

    messages = answered.findings.get_column("message").to_list()
    assert [message.split("states a ")[1].split(" here")[0] for message in messages] == [
        "non-null assertion",
        "`any`",
        "suppression comment",
    ]
