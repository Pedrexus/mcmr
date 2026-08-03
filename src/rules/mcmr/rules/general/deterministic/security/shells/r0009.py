import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table
from ......table.relations import SyntaxTable


@rule("ALL-SECU0004")
def credential_written_into_source(
    subject: Table[SyntaxFact], *, also_secret: tuple[str, ...] = ()
) -> RuleQuery[int]:
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
    relations = SyntaxTable(table=subject)
    facts = subject.lazy(SyntaxRelation.FACTS)
    nodes = relations.nodes
    children = relations.children
    secrets = [
        "password",
        "passwd",
        "passphrase",
        "secret",
        "token",
        "credential",
        "key",
        *also_secret,
    ]
    locations = ["file", "path", "env", "url", "name", "field", "header", "id", "type", "var"]
    nonsecret_key_modifiers = [
        "cache",
        "foreign",
        "lookup",
        "mapping",
        "partition",
        "primary",
        "public",
        "sort",
    ]

    def secret_name(name: pl.Expr) -> pl.Expr:
        words = (
            name.str.replace_all(r"([a-z0-9])([A-Z])", "${1} ${2}")
            .str.replace_all(r"([A-Z])([A-Z][a-z])", "${1} ${2}")
            .str.to_lowercase()
            .str.extract_all(r"[a-z0-9]+")
        )
        nonsecret_key = (words.list.last() == "key") & words.list.eval(
            pl.element().is_in(nonsecret_key_modifiers)
        ).list.any()
        return (
            words.list.eval(pl.element().is_in(secrets)).list.any()
            & (words.list.join("|") != "key")
            & ~words.list.last().is_in(locations)
            & ~nonsecret_key
        )

    def placeholder(literal: pl.Expr) -> pl.Expr:
        written = literal.str.strip_chars("\"'` ").str.to_lowercase()
        return (
            (written == "")
            | written.is_in(["none", "null", "changeme", "change_me", "todo", "xxx", "example"])
            | written.str.contains("your|<|placeholder|dummy")
        )

    bindings = (
        nodes.filter(pl.col("kind") == "binding")
        .filter(secret_name(pl.col("name")))
        .select(
            "fact_id",
            pl.col("ordinal").alias("parent_ordinal"),
            pl.col("name").alias("binding_name"),
        )
    )
    assigned = (
        children.join(bindings, on=["fact_id", "parent_ordinal"], how="inner")
        .join(
            relations.with_text(nodes.filter(pl.col("kind") == "text")).select(
                "fact_id",
                pl.col("ordinal").alias("child_ordinal"),
                "text",
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
            ),
            on=["fact_id", "child_ordinal"],
            how="inner",
        )
        .filter(~placeholder(pl.col("text")))
        .select(
            "fact_id",
            pl.col("child_ordinal").alias("finding_order"),
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            pl.concat_str(
                pl.lit("`"),
                pl.col("binding_name"),
                pl.lit("` is assigned credential literal `"),
                pl.col("text"),
                pl.lit("`"),
            ).alias("message"),
        )
    )
    defaults = (
        relations.with_text(nodes.filter(pl.col("kind") == "callable"))
        .select(
            "fact_id",
            pl.col("ordinal").alias("finding_order"),
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            pl.col("text")
            .str.split("\n")
            .list.first()
            .str.extract_all(r"\w+\s*=\s*['\"][^'\"]*['\"]")
            .alias("matched"),
        )
        .explode("matched", empty_as_null=True)
        .with_columns(
            pl.col("matched")
            .str.extract_groups(r"(?P<name>\w+)\s*=\s*(?P<literal>['\"][^'\"]*['\"])")
            .alias("parts")
        )
        .unnest("parts")
        .filter(secret_name(pl.col("name")) & ~placeholder(pl.col("literal")))
        .select(
            "fact_id",
            "finding_order",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` defaults to credential literal `"),
                pl.col("literal"),
                pl.lit("`"),
            ).alias("message"),
        )
    )
    reported = pl.concat([defaults, assigned], how="vertical")
    counts = reported.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    values = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    findings = FindingQuery.build(
        reported,
        pl.col("message"),
        (("credential written into source", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("finding_order"),
    )
    return RuleQuery.integer(values, pl.col("value"), findings=findings)
