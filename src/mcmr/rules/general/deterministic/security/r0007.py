from ..... import rule
from .....facts import SyntaxFact
from .....models import Count


def primitives_named(*written: str) -> set[str]:
    """Return every word some written source states, so `createHash('MD5')` reads as md5."""
    return {
        piece.strip("\"'` ").lower()
        for item in written
        for piece in item.replace("::", ".").split(".")
    }


@rule
def weak_hashing_primitive(subject: SyntaxFact, *, also_broken: tuple[str, ...] = ()) -> Count:
    """Count the calls that reach a hash primitive the world already knows how to break.

    Definition
    ----------
    Read every call a declaration states and report one that reaches MD5, SHA-1, or another digest
    with a published collision. Most languages carry the primitive in the callee name and a
    factory carries it in the literal handed to the call, so both are read and one rule answers
    for `hashlib.md5`, `MD5.Create`, `Md5::new`, and `createHash('md5')`. A broken digest is
    expensive the moment it ships, because a collision lets someone swap the content behind a
    signature that still verifies, and every artifact already signed with it has to be signed
    again by hand.

    Evidence
    --------
    Each finding names the declaration, the call, and the line. The value is how many calls reach
    a broken primitive. A nested call keeps its own node, so `outer(md5(data))` is read once.

    Exceptions
    ----------
    A digest that guards nothing, such as a cache key or a shard bucket, costs nothing when it
    collides, so a call that states it is not used for security is left alone. A project that
    wraps its own name around a broken primitive names that wrapper through `also_broken`, since
    no list of spellings is ever finished.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       signature = hashlib.md5(payload).hexdigest()

    Good
    ~~~~
    .. code-block:: python

       signature = hashlib.sha256(payload).hexdigest()

    References
    ----------
    Generalizes Ruff S324 hashlib-insecure-hash-function
    https://docs.astral.sh/ruff/rules/hashlib-insecure-hash-function/
    Cites "Common Weakness Enumeration", CWE-327, use of a broken or risky cryptographic algorithm
    https://cwe.mitre.org/data/definitions/327.html
    Cites "The First Collision for Full SHA-1"
    https://shattered.io/
    """
    if subject.tree is None:
        return 0
    broken = {"md2", "md4", "md5", "sha1", "sha-1", "ripemd160", *also_broken}
    reported = 0
    for call in subject.tree.of_kind("call"):
        written = [
            child.name or child.text
            for child in call.children
            if child.kind in {"name", "member", "text"}
        ]
        disclaimed = "usedforsecurity=false" in call.text.replace(" ", "").lower()
        reported += bool(broken & primitives_named(call.name, *written)) and not disclaimed
    return reported
