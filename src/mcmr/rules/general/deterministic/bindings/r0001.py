from ..... import rule
from .....facts import InteropFact
from .....models import Occurrence


@rule
def unreached_cross_language_artifact(subject: InteropFact) -> Occurrence:
    """Report an artifact one language declares that no other language reaches.

    Definition
    ----------
    Report a binary, native module, shared library, or kernel a repository declares where nothing
    outside its own language names it. Such an artifact is either dead weight that still has to be
    built, released, and kept compiling, or a seam whose other side was never wired. Both cost, and
    neither is visible in an import graph, because the caller and the callee never share one.

    Evidence
    --------
    Each finding names the artifact, the mechanism it is reached through, the manifest or source
    that declares it, and every file that names it. The result reports whether the artifact stands
    unreached.

    Exceptions
    ----------
    A published binary, a library another repository consumes, and a plugin a host loads at
    runtime all have their callers outside this tree. A project excludes what it ships rather than
    deleting it. A name reached only through a variable this scan cannot follow also reads as
    unreached, which is why the finding names the files it did see.

    Examples
    --------
    A Cargo manifest declaring `mcmr-kernel` that Python spawns is reached and passes. The same
    binary with no Python caller left after a refactor is reported.

    References
    ----------
    Cites "PyO3 user guide", building and distributing a module
    https://pyo3.rs/latest/building-and-distribution.html
    Cites "pybind11 documentation", module creation
    https://pybind11.readthedocs.io/en/stable/reference.html
    Cites "Python Packaging User Guide", entry points and console scripts
    https://packaging.python.org/en/latest/specifications/entry-points/
    """
    return not [
        language
        for language in subject.referencing_languages
        if language not in {subject.declared_language, "manifest"}
    ]
