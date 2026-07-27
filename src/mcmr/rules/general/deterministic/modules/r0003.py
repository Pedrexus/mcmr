from pathlib import PurePosixPath

from ..... import rule
from .....facts import ModuleFact
from .....models import Occurrence


@rule
def module_inception(subject: ModuleFact) -> Occurrence:
    """Report a module named after the package that already contains it.

    Definition
    ----------
    Report a source file whose own name repeats the name of the directory holding it, which reads
    as `parser::parser`, `parser.parser`, or `parser/parser` at every use. The second name carries
    no information, since it does not say what this file holds that its siblings do not, and a
    reader following an import learns nothing from it. The usual cause is a package grown out of
    one file where the original name was kept out of habit, and the repair is to name the file
    after the part it holds or to move its contents into the package entry point.

    Every language that maps a directory onto a namespace takes part, since the defect is in the
    naming rather than in the syntax. A package initializer is never reported, because `__init__`,
    `mod`, and `index` are the names a language reserves for the entry point of a package and none
    of them can repeat a directory name.

    A module a language nests inside another module in one file is out of reach here, because this
    reads the file layout rather than the declarations inside a file.

    Evidence
    --------
    The finding names the module path and the package holding it. The result reports whether the
    module repeats its package name.

    Exceptions
    ----------
    A repository whose layout tool requires the repetition, such as a single-crate workspace that
    pins a path, should exclude those paths rather than rename them. A directory and a file that
    merely share a prefix are not reported, since only an exact repetition is uninformative.

    Examples
    --------
    `parser/parser.py`, `parser/parser.rs`, and `parser/parser.ts` are reported. `parser/lexer.py`,
    `parser/__init__.py`, `parser/mod.rs`, and `parser/index.ts` are not, and neither is
    `parser/parser_table.py`.

    References
    ----------
    Generalizes Clippy module_inception
    https://rust-lang.github.io/rust-clippy/master/index.html#module_inception
    Cites "The Rust Reference", modules and the file layout that declares them
    https://doc.rust-lang.org/reference/items/modules.html
    Cites "Python Packaging User Guide", package and module names
    https://packaging.python.org/en/latest/specifications/name-normalization/
    """
    path = PurePosixPath(subject.span.path)
    return path.stem == path.parent.name
