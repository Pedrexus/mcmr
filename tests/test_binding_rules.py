from mcmr.facts import InteropFact, InteropMechanism, InteropReference, SourceSpan
from mcmr.rules.general.deterministic.bindings.r0001 import unreached_cross_language_artifact
from mcmr.rules.general.deterministic.bindings.r0002 import cross_language_boundary_width


def artifact(*languages: str, declared: str = "rust") -> InteropFact:
    """Build one declared artifact and the languages that name it."""
    return InteropFact(
        key="interop:binary:kernel",
        span=SourceSpan(path="kernel/Cargo.toml"),
        name="kernel",
        mechanism=InteropMechanism.BINARY,
        declared_language=declared,
        referencing_languages=list(languages),
        references=[
            InteropReference(path=f"{language}/caller", language=language)
            for language in languages
        ],
    )


def test_an_artifact_only_its_own_language_names_is_reported() -> None:
    """A seam with one side wired is dead weight that still has to be built and shipped."""
    assert unreached_cross_language_artifact(artifact("rust", "manifest"))
    assert not unreached_cross_language_artifact(artifact("rust", "python"))
    assert unreached_cross_language_artifact(artifact())


def test_the_width_of_a_seam_counts_only_the_languages_that_cross_it() -> None:
    """The declaring language and the manifests describing it are not crossings."""
    assert cross_language_boundary_width(artifact("rust", "manifest")) == 0
    assert cross_language_boundary_width(artifact("rust", "python", "manifest")) == 1
    assert cross_language_boundary_width(artifact("python", "cpp", "typescript")) == 3
