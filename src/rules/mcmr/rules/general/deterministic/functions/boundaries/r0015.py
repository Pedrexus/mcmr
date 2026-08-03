import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import SyntaxFact
from ......query import FindingQuery, RuleQuery
from ......table import SyntaxRelation, Table


@rule("ALL-FUNC0011")
def reflective_scope_read(
    subject: Table[SyntaxFact],
    *,
    reflections: tuple[str, ...] = ("locals", "vars", "globals", "eval", "exec"),
) -> RuleQuery[int]:
    """Count places one callable reads or rewrites its own scope reflectively.

    Definition
    ----------
    Report a call inside a callable that hands back the scope itself rather than a value from it,
    such as `locals`, `vars`, `globals`, `eval`, and `exec`. The value is the number of such calls,
    and `reflections` names them, so a language with another spelling is configured rather than
    reimplemented.

    A body doing this stops being readable statically by anything, including its own reader. A
    name that looks dead may be reached through the dictionary, a name that looks bound may be
    rewritten before it is used, and a rename that a tool would otherwise perform safely becomes a
    silent break. Pylint meets the same wall from the other side and downgrades `unused-variable`
    to `possibly-unused-variable` wherever `locals` appears, hedging once per name. Naming the
    reflection once says the same thing about the cause instead of about each symptom.

    Only a bare call counts. A member call such as `self.locals()` is a method of the project
    rather than the builtin that opens the scope.

    Evidence
    --------
    The finding names the declaration and counts the reflective calls inside it. The count is per
    call rather than per name, because each one is a separate place the scope escapes. The value is
    the number of reflective calls inside this declaration.

    Exceptions
    ----------
    A debugging helper, a template engine, and a serializer written against a frame are the places
    this is deliberate, and they are worth marking as such once. Passing an explicit mapping to
    `eval` narrows the blast radius but does not remove it, so it is still reported.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def render(template, title, author):
           return template.format(**locals())

    Good
    ~~~~
    .. code-block:: python

       def render(template, title, author):
           return template.format(title=title, author=author)

    References
    ----------
    Adapts Pylint W0641 possibly-unused-variable
    https://pylint.readthedocs.io/en/latest/user_guide/messages/warning/possibly-unused-variable.html
    Cites "The Python Standard Library", `locals`, whose result is explicitly not writeable back
    https://docs.python.org/3/library/functions.html#locals
    Cites "Eval Really Is Dangerous", on why the unsafety of `eval` is hard to enumerate
    https://nedbatchelder.com/blog/201206/eval_really_is_dangerous.html
    """
    facts = subject.lazy(SyntaxRelation.FACTS)
    callables = facts.filter(pl.col("kind") == "callable")
    calls = (
        subject.lazy(SyntaxRelation.NODES)
        .filter((pl.col("kind") == "call") & pl.col("name").is_in(list(reflections)))
        .join(callables.select("fact_id", "qualname"), on="fact_id", how="inner")
    )
    counts = calls.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    values = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    findings = FindingQuery.build(
        calls,
        pl.concat_str(
            pl.lit("`"),
            pl.col("name"),
            pl.lit("` reflectively exposes the scope of `"),
            pl.col("qualname"),
            pl.lit("`"),
        ),
        (("reflective scope read", pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("ordinal"),
    )
    return RuleQuery.integer(values, pl.col("value"), findings=findings)
