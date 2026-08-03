import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable


@rule("ALL-SECU0002")
def weak_hashing_primitive(
    subject: Table[SyntaxFact],
    *,
    also_broken: tuple[str, ...] = (),
    factories: tuple[str, ...] = ("createhash", "getinstance", "newdigest"),
) -> RuleQuery[int]:
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
    no list of spellings is ever finished. The `factories` setting names call spellings whose
    literal arguments carry the primitive rather than the callee itself.

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
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    children = relations.children
    broken = ["md2", "md4", "md5", "sha1", "sha-1", "ripemd160", *also_broken]
    calls = relations.with_text(nodes.filter(pl.col("kind") == "call")).select(
        "fact_id",
        pl.col("ordinal").alias("call_ordinal"),
        pl.col("name").alias("call_name"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        pl.col("name").str.to_lowercase().str.replace_all("::", ".").alias("callee"),
        pl.col("text").str.replace_all(" ", "").str.to_lowercase().alias("call_text"),
    )
    arguments = (
        children.select(
            "fact_id",
            pl.col("parent_ordinal").alias("call_ordinal"),
            "child_ordinal",
        )
        .join(
            relations.with_text(
                nodes.filter(pl.col("kind").is_in(["name", "member", "text"]))
            ).select("fact_id", pl.col("ordinal").alias("child_ordinal"), "name", "text"),
            on=["fact_id", "child_ordinal"],
            how="inner",
        )
        .with_columns(
            pl.when(pl.col("name") != "")
            .then(pl.col("name"))
            .otherwise(pl.col("text"))
            .str.strip_chars("\"'` ")
            .str.to_lowercase()
            .str.replace_all("::", ".")
            .str.split(".")
            .alias("parts")
        )
        .explode("parts", empty_as_null=True)
        .filter(pl.col("parts").is_in(broken))
        .group_by("fact_id", "call_ordinal", maintain_order=True)
        .agg(pl.col("parts").unique().sort().alias("argument_broken"))
    )
    reported = (
        calls.join(arguments, on=["fact_id", "call_ordinal"], how="left")
        .with_columns(
            pl.col("callee").str.split(".").list.last().alias("launched"),
            pl.col("callee")
            .str.split(".")
            .list.eval(pl.element().filter(pl.element().is_in(broken)))
            .alias("callee_broken"),
            pl.col("argument_broken")
            .fill_null(pl.lit([], dtype=pl.List(pl.String)))
            .alias("argument_broken"),
        )
        .with_columns(
            pl.when(pl.col("launched").is_in(list(factories)))
            .then(pl.col("argument_broken"))
            .otherwise(pl.lit([], dtype=pl.List(pl.String)))
            .alias("selected_arguments")
        )
        .with_columns(
            pl.concat_list("callee_broken", "selected_arguments")
            .list.unique()
            .list.sort()
            .alias("matched")
        )
        .filter(
            ~pl.col("call_text").str.contains("usedforsecurity=false", literal=True)
            & (
                (pl.col("callee_broken").list.len() > 0)
                | (
                    pl.col("launched").is_in(list(factories))
                    & (pl.col("selected_arguments").list.len() > 0)
                )
            )
        )
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
            pl.col("call_name"),
            pl.lit("` reaches broken hash primitive `"),
            pl.col("matched").list.join("`, `"),
            pl.lit("`"),
        ),
        (("weak hashing primitive", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("call_ordinal"),
    )
    return RuleQuery.integer(joined, pl.col("value"), findings=findings)
