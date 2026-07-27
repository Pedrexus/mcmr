from ..... import rule
from .....facts import SyntaxFact, SyntaxNode
from .....models import Count


def asks_for_a_shell(written: str) -> bool:
    """Judge whether a launcher was told to hand its command line to a shell by name."""
    stated = written.replace(" ", "").lower()
    asked = ("shell=true", "shell:true", "usesshell", "/bin/sh", "/bin/bash", "cmd.exe")
    return any(marker in stated for marker in asked)


def is_a_command_line(argument: SyntaxNode) -> bool:
    """Judge whether one argument assembles a command line rather than combining two values.

    An operator alone does not say what it joined. Concatenating a command with a variable and
    combining two enumerators with a bitwise or are the same `operation` node in every language,
    so the part of the command that was written down has to be somewhere inside it. Requiring that
    is what keeps `exec_tag::sync | exec_tag::timer` from reading as a command an attacker reaches.
    """
    return argument.kind == "operation" and any(held.kind == "text" for held in argument.walk())


@rule
def command_built_from_a_shell_string(
    subject: SyntaxFact, *, also_through_a_shell: tuple[str, ...] = ()
) -> Count:
    """Count the process launches that hand a command line to a shell.

    Definition
    ----------
    Report a spawn that runs through a shell rather than through an argument list. A shell reads
    the string it receives and treats a space, a quote, a backtick, and a statement separator as
    syntax, so any value that reaches that string can append a second command the caller never
    wrote. Handing the launcher a list keeps every argument separate no matter what it holds,
    which is why the list form is the repair rather than another round of escaping. One rule
    answers for `os.system`, `shell_exec`, `child_process.exec`, and a command asked for `sh -c`.

    A command line built from parts is one whose first argument combines values and states part of
    the command itself. The operator alone does not say what it joined, so a piece of the command
    has to be written down inside the expression. Without that, two flags combined with a bitwise
    or read as an assembled command line in every brace language.

    Evidence
    --------
    Each finding names the declaration, the launcher, and the line. The value is how many launches
    reach a shell. The launcher is read from the last segment of the callee, so `System.out` and
    `os.system` stay apart.

    Exceptions
    ----------
    A launcher that says it does not want a shell, such as one written with `shell=False`, is left
    alone, and so is one handed an argument list, because a list is the shape this rule asks for.
    A launcher handed one constant command line has nothing an attacker can reach, so only a shell
    asked for by name and a command line built from parts are reported. An argument combining two
    values that names no part of a command, the way `exec_tag::sync | exec_tag::timer` does, is
    not a command line and is left alone. A project that wraps its own name around a shell names
    that wrapper through `also_through_a_shell`.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       subprocess.run(f"git checkout {ref}", shell=True)
       os.popen("git checkout " + ref)

    Good
    ~~~~
    .. code-block:: python

       subprocess.run(["git", "checkout", ref])

    .. code-block:: cpp

       state.exec(nvbench::exec_tag::sync | nvbench::exec_tag::timer, run);

    References
    ----------
    Generalizes Ruff S602 subprocess-popen-with-shell-equals-true
    https://docs.astral.sh/ruff/rules/subprocess-popen-with-shell-equals-true/
    Generalizes Ruff S604 call-with-shell-equals-true
    https://docs.astral.sh/ruff/rules/call-with-shell-equals-true/
    Generalizes Ruff S605 start-process-with-a-shell
    https://docs.astral.sh/ruff/rules/start-process-with-a-shell/
    Cites "Common Weakness Enumeration", CWE-78, improper neutralization in an OS command
    https://cwe.mitre.org/data/definitions/78.html
    """
    if subject.tree is None:
        return 0
    shell_only = {"system", "shell_exec", "passthru", "getoutput", "getstatusoutput"}
    shell_only.update(also_through_a_shell)
    launcher = {"run", "call", "spawn", "spawnsync", "exec", "execsync", "popen", "command"}
    reported = 0
    for call in subject.tree.of_kind("call"):
        launched = call.name.lower().replace("::", ".").rsplit(".", 1)[-1]
        arguments = call.children[1:]
        built_from_parts = bool(arguments) and is_a_command_line(arguments[0])
        refuses_a_shell = "shell=false" in call.text.replace(" ", "").lower()
        wants_a_shell = built_from_parts or asks_for_a_shell(call.text)
        reported += launched in shell_only or (
            launched in launcher and wants_a_shell and not refuses_a_shell
        )
    return reported
