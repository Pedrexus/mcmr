from ..... import rule
from .....facts import InteropFact
from .....models import Count


@rule
def cross_language_boundary_width(subject: InteropFact) -> Count:
    """Measure how many languages depend on one cross-language artifact.

    Definition
    ----------
    Count the distinct languages that name one declared artifact, excluding the language that
    declares it and the manifests that describe it. Every language on that list depends on the
    artifact's exact name, its exact interface, and its build. A seam two languages cross is a
    contract, and one that four cross is infrastructure, and it needs a stated interface, a
    version, and a test on each side rather than a name that happens to match.

    Evidence
    --------
    Each finding names the artifact, its mechanism, and each language that reaches it with the
    files that do. The value is the number of reaching languages.

    Exceptions
    ----------
    A shared runtime library is meant to be reached widely, and a project raises its ceiling
    rather than splitting it. A name matched only by coincidence would inflate the count, which is
    why a reference is recorded only where the name is stated as a literal string.

    Examples
    --------
    A CUDA kernel loaded from Python and wrapped in C++ returns `2` and deserves a stated
    interface. A binary only its own tests spawn returns `0`.

    References
    ----------
    Cites "CUDA C++ Programming Guide", the runtime and driver APIs
    https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html
    Cites "PyO3 user guide", the Python and Rust boundary
    https://pyo3.rs/latest/
    Cites "Release It", on integration points
    """
    return len(
        {
            language
            for language in subject.referencing_languages
            if language not in {subject.declared_language, "manifest"}
        }
    )
