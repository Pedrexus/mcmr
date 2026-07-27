import re

from ..... import rule
from .....facts import SyntaxFact
from .....models import Count


def words_of(name: str) -> list[str]:
    """Split one identifier into lowercase words, so `apiKey` and `API_KEY` both read alike."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return re.findall(r"[a-z0-9]+", spaced.lower())


def promises_secrecy(name: str, unguessable: set[str]) -> bool:
    """Judge whether a bound name promises a value nobody may predict."""
    spelled = words_of(name)
    return bool(unguessable & set(spelled)) and spelled != ["key"]


@rule
def unseeded_randomness_for_secrets(
    subject: SyntaxFact, *, also_predictable: tuple[str, ...] = ()
) -> Count:
    """Count the unguessable values an ordinary random generator produced.

    Definition
    ----------
    Read every binding whose name promises a value nobody may predict, such as a token, a nonce,
    a session id, or an api key, then report the calls beneath it that reach a general purpose
    pseudo random generator. `random`, `Math.random`, `rand`, `srand`, and `thread_rng` all run a
    fast deterministic sequence that an observer recovers after collecting a handful of outputs,
    so a token minted from one is guessable by anyone patient enough to collect them. The cost
    arrives as account takeover rather than as a crash a test would have caught, which is why no
    amount of later testing finds it.

    Evidence
    --------
    Each finding names the declaration, the bound name, and the generator the call reaches. The
    value is how many predictable draws land under a name that promised secrecy.

    Exceptions
    ----------
    Randomness that guards nothing is fine, so a retry delay, a sampled batch, or a test fixture
    is never reported, because the name never claimed the value had to be unguessable. A
    generator built for secrets, such as `secrets`, `os.urandom`, `crypto.getRandomValues`, or
    `SecureRandom`, is the answer this rule asks for and stays welcome even under a secret name.
    A bare `key` is a map key far more often than a credential, so it takes a qualifier to count.
    A project with its own wrapper around an ordinary generator names it through
    `also_predictable`.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: javascript

       const sessionToken = Math.random().toString(36).slice(2)

    Good
    ~~~~
    .. code-block:: javascript

       const sessionToken = crypto.randomUUID()

    References
    ----------
    Generalizes Ruff S311 suspicious-non-cryptographic-random-usage
    https://docs.astral.sh/ruff/rules/suspicious-non-cryptographic-random-usage/
    Cites "Common Weakness Enumeration", CWE-338, weak pseudo random number generation
    https://cwe.mitre.org/data/definitions/338.html
    Cites "The Python Standard Library", `secrets`, secure random numbers
    https://docs.python.org/3/library/secrets.html
    """
    if subject.tree is None:
        return 0
    unguessable = {"token", "secret", "key", "password", "nonce", "salt", "otp", "csrf", "session"}
    predictable = {
        "random",
        "rand",
        "randint",
        "randrange",
        "randbytes",
        "getrandbits",
        "shuffle",
        "sample",
        "choice",
        "uniform",
        "srand",
        "mt_rand",
        "thread_rng",
        "nextint",
        *also_predictable,
    }
    secure = {
        "secrets",
        "crypto",
        "urandom",
        "getrandom",
        "randombytes",
        "randomuuid",
        "getrandomvalues",
        "securerandom",
        "osrng",
    }
    reported = 0
    for holder in subject.tree.of_kind("binding"):
        if not promises_secrecy(holder.name, unguessable):
            continue
        for call in holder.of_kind("call"):
            segments = call.name.lower().replace("::", ".").split(".")
            reported += segments[-1] in predictable and not secure & set(segments)
    return reported
