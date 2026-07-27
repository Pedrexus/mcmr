import re

from ..... import rule
from .....facts import SyntaxFact
from .....models import Count


def words_of(name: str) -> list[str]:
    """Split one identifier into lowercase words, so `apiKey` and `API_KEY` both read alike."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return re.findall(r"[a-z0-9]+", spaced.lower())


def promises_a_secret(name: str, secret: set[str]) -> bool:
    """Judge whether a name promises a secret rather than saying where one lives."""
    location = {"file", "path", "env", "url", "name", "field", "header", "id", "type", "var"}
    spelled = words_of(name)
    return bool(secret & set(spelled)) and spelled != ["key"] and spelled[-1] not in location


def is_a_placeholder(literal: str) -> bool:
    """Judge whether a literal is a template a reader has to replace rather than a live value."""
    written = literal.strip("\"'` ").lower()
    return (
        not written
        or written in {"none", "null", "changeme", "change_me", "todo", "xxx", "example"}
        or any(hint in written for hint in ("your", "<", "placeholder", "dummy"))
    )


@rule
def credential_written_into_source(
    subject: SyntaxFact, *, also_secret: tuple[str, ...] = ()
) -> Count:
    """Count the credentials a declaration writes down beside a name that promises a secret.

    Definition
    ----------
    Report a literal bound to a name such as `password`, `api_key`, `token`, or `secret`, whether
    the source assigns it or writes it as a default in a signature. A secret written into source
    ships everywhere the source ships, so it reaches every clone, every image built from the
    repository, and every copy of the history, and rotating it later means hunting down all of
    them. The real cost is that the value keeps working long after the commit that leaked it is
    forgotten, which turns a one line mistake into an open door nobody is watching.

    Evidence
    --------
    Each finding names the declaration, the bound name, and the literal as the source writes it.
    The value is how many literals a declaration writes down under a name that promises a secret.

    Exceptions
    ----------
    A template a reader is meant to replace is not a credential, so an empty literal and a
    placeholder such as `changeme` or `your-api-key` are left alone. A name that says where a
    secret lives rather than what it is, such as `password_file` or `token_env`, holds a location
    and is left alone too, and a bare `key` is a map key far more often than a credential. A
    literal handed to a call under a keyword is the same defect, and a language neutral tree
    carries the value without the keyword that named it, so that shape is left to the linter of
    the language that can read it. A project with its own vocabulary names it through
    `also_secret`.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def connect(host, password="hunter2"):
           ...

    Good
    ~~~~
    .. code-block:: python

       def connect(host, password=os.environ["DB_PASSWORD"]):
           ...

    References
    ----------
    Generalizes Ruff S105 hardcoded-password-string
    https://docs.astral.sh/ruff/rules/hardcoded-password-string/
    Generalizes Ruff S106 hardcoded-password-func-arg
    Generalizes Ruff S107 hardcoded-password-default
    https://docs.astral.sh/ruff/rules/hardcoded-password-default/
    Cites "Common Weakness Enumeration", CWE-798, use of hard-coded credentials
    https://cwe.mitre.org/data/definitions/798.html
    Cites "OWASP Top Ten", 2021 A07, identification and authentication failures
    https://owasp.org/Top10/A07_2021-Identification_and_Authentication_Failures/
    """
    if subject.tree is None:
        return 0
    secret = {"password", "passwd", "passphrase", "secret", "token", "credential", "key"}
    secret.update(also_secret)
    reported = 0
    for holder in subject.tree.walk():
        if holder.kind == "binding" and promises_a_secret(holder.name, secret):
            reported += sum(
                not is_a_placeholder(child.text)
                for child in holder.children
                if child.kind == "text"
            )
        if holder.kind == "callable":
            reported += sum(
                promises_a_secret(name, secret) and not is_a_placeholder(literal)
                for name, literal in re.findall(
                    r"(\w+)\s*=\s*(['\"][^'\"]*['\"])", holder.text.split("\n", 1)[0]
                )
            )
    return reported
