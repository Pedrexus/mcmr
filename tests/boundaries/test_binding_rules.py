from mcmr.domain.contracts import RuleContract, RuleValue
from mcmr.facts import InteropFact, InteropMechanism, InteropReference, SourceSpan
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import cross_language_boundary_width, unreached_cross_language_artifact
from mcmr.table import fact_table


def artifact(*languages: str, declared: str = "rust") -> InteropFact:
    """Build one declared artifact and the languages that name it."""
    return InteropFact(
        key="interop:binary:kernel",
        span=SourceSpan(path="kernel/Cargo.toml"),
        name="kernel",
        mechanism=InteropMechanism.BINARY,
        declared_language=declared,
        references=[
            InteropReference(path=f"{language}/caller", language=language)
            for language in languages
        ],
    )


def value(rule: RuleContract, subject: InteropFact) -> RuleValue:
    """Run one binding rule once over one in-memory typed table."""
    table = fact_table(InteropFact, [subject])
    result = rule.invoke_table(table, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic binding rule returned a model query")
    return scalar_frame_value(result.values.collect())


def test_an_artifact_only_its_own_language_names_is_reported() -> None:
    """A seam with one side wired is dead weight that still has to be built and shipped."""
    assert value(unreached_cross_language_artifact, artifact("rust", "manifest")) is True
    assert value(unreached_cross_language_artifact, artifact("rust", "python")) is False
    assert value(unreached_cross_language_artifact, artifact()) is True


def test_the_width_of_a_seam_counts_only_the_languages_that_cross_it() -> None:
    """The declaring language and the manifests describing it are not crossings."""
    assert value(cross_language_boundary_width, artifact("rust", "manifest")) == 0
    assert value(cross_language_boundary_width, artifact("rust", "python", "manifest")) == 1
    assert value(cross_language_boundary_width, artifact("python", "cpp", "typescript")) == 3
