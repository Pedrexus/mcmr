import re

from ..... import rule
from .....facts import SyntaxFact, SyntaxNode
from .....models import Count

# One name as any language writes it, keeping the dots a member call needs and the bang a Rust
# macro carries, so `console.log` and `println!` arrive whole rather than in pieces.
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*!?")

# What separates one path into the parts a reader recognizes, so `tests` and `cli` are found as
# whole segments and a file named `bindings.py` is never mistaken for a `bin` directory.
_SEGMENT = re.compile(r"[\\/._-]")


def stated_artifacts(node: SyntaxNode, artifacts: tuple[str, ...]) -> int:
    """Return how many debug artifacts one node states.

    A frontend that resolved the name says so, and reading that name is exact. A macro or a bare
    keyword arrives with no name and nothing beneath it, and only then is the node's own text read
    for the words it holds.
    """
    if node.name:
        return node.name in artifacts
    if node.children:
        return 0
    return sum(word in artifacts for word in _WORD.findall(node.text))


@rule
def debug_artifact_left_behind(
    subject: SyntaxFact,
    *,
    artifacts: tuple[str, ...] = (
        "print",
        "printf",
        "println!",
        "eprintln!",
        "dbg!",
        "console.log",
        "console.debug",
        "breakpoint",
        "debugger",
        "pdb.set_trace",
        "set_trace",
    ),
    exempt_segments: tuple[str, ...] = (
        "test",
        "tests",
        "cli",
        "main",
        "bin",
        "script",
        "scripts",
        "example",
        "examples",
    ),
) -> Count:
    """Count console prints and debugger breakpoints left behind in ordinary code.

    Definition
    ----------
    Report a call or a statement naming a debug artifact inside a declaration that is neither a
    test nor a command line entry point. `print` in Python, `println!` and `dbg!` in Rust,
    `console.log` in TypeScript, and `printf` in C are the same artifact under five spellings, and
    so are `breakpoint`, `debugger`, and `set_trace`.

    The cost is real in both directions. A print writes to a stream nobody configured, so it cannot
    be filtered, routed, or turned off the way a logger can, and it follows the code into
    production where it slows a hot path and can leak whatever the developer was inspecting. A
    breakpoint is worse, since it stops a program that has no terminal attached and hangs it.

    Evidence
    --------
    Each finding names the declaration, the artifact, and the line. The value is the number of
    artifacts left behind.

    Exceptions
    ----------
    A file whose path holds a segment such as `tests`, `cli`, `bin`, or `main` is where writing to
    the console is the job, so nothing there is reported. Path segments are read whole, which keeps
    a module named `bindings` out of the `bin` exemption. A logger call is never an artifact, since
    a project that configured one already decided where its output goes. A name a frontend resolved
    is trusted as it stands, and only a bare macro or keyword falls back to reading text, where a
    matching word inside a string or a comment on the same line can be read as a call.
    `exempt_segments` is that list of path segments and `artifacts` is the list of debug names, so
    a project with its own console wrapper or its own script directory states them rather than
    living with the defaults.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def charge(order):
           print(order.card)
           breakpoint()
           return gateway.charge(order)

    Good
    ~~~~
    .. code-block:: python

       def charge(order):
           logger.debug("charging %s", order.id)
           return gateway.charge(order)

    References
    ----------
    Generalizes Ruff T201 print
    Generalizes Ruff T100 debugger
    Generalizes Clippy dbg_macro
    Generalizes Clippy print_stdout
    https://rust-lang.github.io/rust-clippy/master/index.html#dbg_macro
    Generalizes ESLint no-console
    Generalizes ESLint no-debugger
    https://eslint.org/docs/latest/rules/no-console
    """
    segments = set(_SEGMENT.split(subject.span.path.lower()))
    if subject.tree is None or segments.intersection(exempt_segments):
        return 0
    return sum(
        stated_artifacts(node, artifacts)
        for node in subject.tree.of_kind("call", "effect", "expression")
    )
