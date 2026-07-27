from mcmr.facts import ErasableConstruct, EscapeHatch, ModuleSurfaceFact, SourceSpan
from mcmr.rules.typescript.deterministic.modules.r0001 import star_reexport_surface
from mcmr.rules.typescript.deterministic.modules.r0002 import relative_import_depth
from mcmr.rules.typescript.deterministic.types.r0001 import non_erasable_construct
from mcmr.rules.typescript.deterministic.types.r0002 import escape_hatch_density
from tests.conftest import measured

SPAN = SourceSpan(path="src/index.ts")


def surface(
    *,
    star_reexports: tuple[str, ...] = (),
    named_reexport_count: int = 0,
    deepest_relative_import: int = 0,
    deepest_relative_specifier: str = "",
    physical_line_count: int = 0,
    erasable_violations: tuple[ErasableConstruct, ...] = (),
    escape_hatches: tuple[EscapeHatch, ...] = (),
) -> ModuleSurfaceFact:
    """Build the surface one TypeScript module publishes."""
    return ModuleSurfaceFact(
        key="surface:index",
        span=SPAN,
        language="typescript",
        star_reexport_count=len(star_reexports),
        star_reexports=list(star_reexports),
        named_reexport_count=named_reexport_count,
        deepest_relative_import=deepest_relative_import,
        deepest_relative_specifier=deepest_relative_specifier,
        physical_line_count=physical_line_count,
        erasable_violations=list(erasable_violations),
        escape_hatches=list(escape_hatches),
    )


def test_a_wholesale_reexport_is_counted_and_a_named_one_is_not() -> None:
    """A barrel that names its exports states a contract, one that stars them states a wish."""
    subject = surface(
        star_reexports=("./UserService", "./internal/userValidation"), named_reexport_count=9
    )

    assert star_reexport_surface(subject).value == 2
    assert star_reexport_surface(surface(named_reexport_count=9)).value == 0


def test_a_wholesale_reexport_finding_names_the_module_it_republishes() -> None:
    """A count of two named neither of the two files whose internals became public."""
    answer = star_reexport_surface(surface(star_reexports=("./internal/userValidation",)))

    assert answer.findings[0].message == (
        "`src/index.ts` re-exports everything `./internal/userValidation` happens to export, so a "
        "helper added there joins this module's contract unreviewed"
    )
    assert answer.findings[0].span.location == "src/index.ts:1"
    assert measured(answer.findings[0]) == {
        "wholesale re-exports": 1,
        "named re-exports beside them": 0,
    }


def test_the_deepest_climb_is_what_a_module_reports() -> None:
    """One import reaching three levels up says the two files are in different parts."""
    subject = surface(deepest_relative_import=3, deepest_relative_specifier="../../../models/user")
    answer = relative_import_depth(subject)

    assert answer.value == 3
    assert answer.findings[0].message == (
        "`src/index.ts` imports through `../../../models/user`, which climbs 3 directories out of "
        "its own"
    )
    assert measured(answer.findings[0]) == {"directories it climbs": 3}
    assert relative_import_depth(surface()).value == 0
    assert relative_import_depth(surface()).findings == ()


def test_every_construct_that_survives_stripping_is_counted() -> None:
    """These are the declarations that generate JavaScript rather than disappearing."""
    subject = surface(
        physical_line_count=40,
        erasable_violations=(
            ErasableConstruct(kind="enum", name="Status", line=3),
            ErasableConstruct(kind="parameter_property", name="limit", line=9),
        ),
    )
    answer = non_erasable_construct(subject)

    assert answer.value == 2
    assert answer.findings[1].message == (
        "`limit` is a parameter property, which generates JavaScript rather than disappearing "
        "with the types"
    )
    assert answer.findings[1].span.location == "src/index.ts:9"
    assert measured(answer.findings[1]) == {
        "constructs stripping cannot erase": 2,
        "lines in the module": 40,
    }
    assert non_erasable_construct(surface()).value == 0


def test_escape_hatch_density_is_measured_against_the_lines_that_carry_it() -> None:
    """One assertion is a decision, and a module full of them is no longer typed."""
    subject = surface(
        physical_line_count=200,
        escape_hatches=tuple(EscapeHatch(kind="assertion", line=index) for index in range(1, 11)),
    )
    answer = escape_hatch_density(subject)

    assert answer.value == 5.0
    assert answer.findings[0].message == (
        "`src/index.ts` states a type assertion here, one of 10 places it steps around its own "
        "types"
    )
    assert answer.findings[0].span.location == "src/index.ts:1"
    assert measured(answer.findings[0]) == {
        "hatches in the module": 10,
        "lines in the module": 200,
        "share of the module": 5.0,
    }
    assert escape_hatch_density(surface(physical_line_count=0)).value == 0.0


def test_every_kind_of_hatch_is_named_in_words_a_reader_recognizes() -> None:
    """A finding stating `non_null` names a field of the fact rather than what the source says."""
    subject = surface(
        physical_line_count=8,
        escape_hatches=(
            EscapeHatch(kind="non_null", line=2),
            EscapeHatch(kind="any", line=4),
            EscapeHatch(kind="ignore_comment", line=6),
        ),
    )
    answer = escape_hatch_density(subject)

    assert [
        finding.message.split("states a ")[1].split(" here")[0] for finding in answer.findings
    ] == [
        "non-null assertion",
        "`any`",
        "suppression comment",
    ]
