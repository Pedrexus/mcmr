from ..... import rule
from .....facts import ModuleFact
from .....models import Count


@rule
def non_ascii_source_path(subject: ModuleFact) -> Count:
    """Count path components outside ASCII on the way to one source file.

    Definition
    ----------
    Read the repository-relative path of every source file and report each component holding a
    character outside ASCII. The value is the number of such components, so a file named in one
    alphabet under a directory named in another counts twice.

    A path is not read only by the editor that displays it. An archive rewrites it under its own
    encoding, a build system interpolates it into a command line, a container image copies it onto
    a filesystem that normalizes Unicode by different rules, and a shell on another platform quotes
    it by rules nobody remembers. Each of those is a place where a name outside ASCII stops being
    the same name, and the failure surfaces far from the file that caused it.

    Evidence
    --------
    The finding names the file and the language that wrote it. The value counts components rather
    than characters, because a component is the unit a filesystem, an archive, and an import
    statement each address.

    Exceptions
    ----------
    A repository whose readers share one alphabet and whose toolchain is fixed can carry these
    names deliberately, which is a decision to record once rather than a finding to silence per
    file. Content that is not source is not read here, since the rule judges source files.

    Examples
    --------
    Bad
    ~~~
    `src/café/lector.py` reports twice, once for the directory and once for the file.

    Good
    ~~~~
    `src/cafe/reader.py` reads the same everywhere it is written down.

    References
    ----------
    Generalizes Pylint W2402 non-ascii-file-name
    https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/non-ascii-file-name.html
    Cites "PEP 3131, Supporting Non-ASCII Identifiers", which restricts what a module name may hold
    https://peps.python.org/pep-3131/
    Cites "Unicode Standard Annex 15", normalization forms and why two spellings compare unequal
    https://unicode.org/reports/tr15/
    """
    return sum(not component.isascii() for component in subject.span.path.split("/"))
