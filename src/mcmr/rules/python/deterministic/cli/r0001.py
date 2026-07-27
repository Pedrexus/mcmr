from ..... import rule
from .....facts import CallFact
from .....models import Count


@rule
def argparse_cli_construction(subject: CallFact) -> Count:
    """Count CLI parsers that bypass the configured Cyclopts foundation.

    Definition
    ----------
    Resolve module, direct, and aliased imports of `argparse.ArgumentParser`. Count each proven
    construction. The project preference is to register typed callables with `cyclopts.App`
    instead of maintaining a second command schema in parser-building code.

    Evidence
    --------
    Each finding identifies the constructor call and records both the observed and preferred CLI
    framework. Lexical assignments and parameters that shadow an import suppress the finding. The
    value is the number of proven `argparse.ArgumentParser` constructions.

    Exceptions
    ----------
    Libraries that extend an external argparse parser, compatibility shims, and generated or
    vendored code may disable this project preference. Merely importing argparse for a compatible
    formatter or namespace does not count.

    Examples
    --------
    Bad
    ~~~
    `parser = argparse.ArgumentParser()` starts a hand-maintained parser command tree.

    Good
    ~~~~
    `app.command(project.build)` exposes the typed callable as the command boundary.

    References
    ----------
    Cites "Cyclopts documentation"
    https://cyclopts.readthedocs.io/en/latest/
    Cites "The Python Standard Library", argparse
    https://docs.python.org/3/library/argparse.html
    """
    return subject.count_calls("argparse.ArgumentParser")
