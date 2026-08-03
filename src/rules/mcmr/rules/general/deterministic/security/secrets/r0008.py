import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table


@rule("ALL-SECU0003")
def unseeded_randomness_for_secrets(
    subject: Table[SyntaxFact], *, also_predictable: tuple[str, ...] = ()
) -> RuleQuery[int]:
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
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = subject.lazy(SyntaxRelation.NODES)
    secret = ["token", "secret", "key", "password", "nonce", "salt", "otp", "csrf", "session"]
    predictable = [
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
    ]
    secure = [
        "secrets",
        "crypto",
        "urandom",
        "getrandom",
        "randombytes",
        "randomuuid",
        "getrandomvalues",
        "securerandom",
        "osrng",
    ]
    name_words = (
        pl.col("name")
        .str.replace_all(r"([a-z0-9])([A-Z])", "${1} ${2}")
        .str.replace_all(r"([A-Z])([A-Z][a-z])", "${1} ${2}")
        .str.to_lowercase()
        .str.extract_all(r"[a-z0-9]+")
    )
    bindings = (
        nodes.filter(pl.col("kind") == "binding")
        .with_columns(name_words.alias("words"))
        .filter(
            pl.col("words").list.eval(pl.element().is_in(secret)).list.any()
            & (pl.col("words").list.join("|") != "key")
        )
        .select(
            "fact_id",
            pl.col("ordinal").alias("binding_ordinal"),
            pl.col("subtree_end").alias("binding_end"),
            pl.col("name").alias("binding_name"),
        )
    )
    calls = (
        nodes.filter(pl.col("kind") == "call")
        .with_columns(
            pl.col("name")
            .str.to_lowercase()
            .str.replace_all("::", ".")
            .str.split(".")
            .alias("segments")
        )
        .filter(
            pl.col("segments").list.last().is_in(predictable)
            & ~pl.col("segments").list.eval(pl.element().is_in(secure)).list.any()
        )
        .select(
            "fact_id",
            "ordinal",
            pl.col("name").alias("call_name"),
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
        )
    )
    reported = bindings.join(calls, on="fact_id", how="inner").filter(
        (pl.col("ordinal") >= pl.col("binding_ordinal"))
        & (pl.col("ordinal") < pl.col("binding_end"))
    )
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    joined = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    findings = FindingQuery.build(
        reported,
        pl.concat_str(
            pl.lit("`"),
            pl.col("binding_name"),
            pl.lit("` promises secrecy but receives predictable output from `"),
            pl.col("call_name"),
            pl.lit("`"),
        ),
        (("unseeded randomness for secrets", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("ordinal"),
    )
    return RuleQuery.integer(joined, pl.col("value"), findings=findings)
