import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....domain.contracts import Unit
from .....facts import FunctionFact
from .....query import FindingQuery, RuleQuery
from .....table import FunctionRelation, Table


@rule("PY-DOCU0001")
def compact_house_docstring(
    subject: Table[FunctionFact], *, maximum_summary: NonNegativeInt = 99
) -> RuleQuery[bool]:
    """Enforce compact self-contained house docstrings where documentation exists.

    Definition
    ----------
    For every docstring a method or a function states, require a nonempty punctuated one-line
    summary within `maximum_summary`. Reject summaries that only send the reader elsewhere, Google
    or NumPy Args and Returns headings, and reStructuredText field lists. Accept compact
    `name: description` lines and require their description to be nonempty. Missing callable
    docstrings are left to dedicated coverage tools, and a module docstring belongs to the module
    family rather than to this one.

    Evidence
    --------
    Each finding points at the callable that owns the docstring and names which of the two shapes
    broke, the summary line or the body beneath it, beside how long the summary runs against what
    this project accepts. More than one violation in the same docstring stays a separate finding.
    The repair is a choice, since only the author knows what the sentence was trying to say.

    Exceptions
    ----------
    A docstring may contain technical reStructuredText sections, examples, directives, URLs, and
    references after its self-contained summary. Attribute documentation and ordinary multiline
    string values are not docstrings. Externally required doc formats can disable the rule at that
    adapter boundary.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def encode(text: str) -> list[int]:
           '''See the tokenizer documentation.

           Args:
               text: Input text.
           Returns:
               Token IDs.
           '''

    Good
    ~~~~
    .. code-block:: python

       def encode(text: str) -> list[int]:
           '''Encode text to token IDs.

           text: Input string to tokenize.
           '''

    References
    ----------
    Cites "PEP 257, Docstring Conventions"
    https://peps.python.org/pep-0257/
    Cites "The Python Developer's Guide"
    https://devguide.python.org/documentation/markup/
    Cites "Ruff documentation", pydocstyle rules
    https://docs.astral.sh/ruff/rules/#pydocstyle-d
    """
    frame = subject.lazy(FunctionRelation.FUNCTIONS).with_columns(
        pl.col("docstring").str.strip_chars().str.split("\n").alias("doc_lines")
    )
    summary = pl.col("doc_lines").list.first().str.strip_chars().fill_null("")
    summary_length = summary.str.len_chars()
    invalid_summary = (
        (summary == "")
        | (summary_length > maximum_summary)
        | ~summary.str.slice(-1).is_in([".", "!", "?"])
        | summary.str.to_lowercase().str.starts_with("see ")
        | summary.str.to_lowercase().str.starts_with("refer to ")
    )
    body_lines = pl.col("doc_lines").list.slice(1)
    line = pl.element()
    stripped_line = pl.element().str.strip_chars()
    missing_label = line.str.contains(r"^[A-Za-z_][A-Za-z0-9_ ]*:\s*$")
    directive = stripped_line.str.starts_with(".. ")
    invalid_body = body_lines.list.eval(
        line.str.to_lowercase().is_in(["args:", "arguments:", "returns:", "parameters", "returns"])
        | line.str.starts_with(":param")
        | line.str.starts_with(":return")
        | line.str.starts_with(":rtype")
        | (missing_label & ~directive)
    ).list.any()
    docstring_present = pl.col("docstring") != ""
    enriched = frame.with_columns(
        summary_length.alias("summary_length"),
        (docstring_present & invalid_summary).alias("invalid_summary"),
        (docstring_present & invalid_body).alias("invalid_body"),
    )
    value = pl.col("invalid_summary") | pl.col("invalid_body")
    measurements = (
        ("characters in the summary", pl.col("summary_length"), Unit.COUNT),
        ("characters this project accepts", pl.lit(maximum_summary), Unit.COUNT),
    )
    summary_findings = FindingQuery.build(
        enriched,
        pl.concat_str(
            pl.lit("the docstring of `"),
            pl.col("name"),
            pl.lit("` opens with "),
            pl.col("summary_length"),
            pl.lit(" characters that do not read as one finished sentence"),
        ),
        measurements,
        predicate=pl.col("invalid_summary"),
        finding_order=pl.lit(0),
        question=pl.concat_str(
            pl.lit("rewrite the first line of `"),
            pl.col("name"),
            pl.lit("` as one sentence under "),
            pl.lit(maximum_summary),
            pl.lit(" characters"),
        ),
    )
    body_findings = FindingQuery.build(
        enriched,
        pl.concat_str(
            pl.lit("the docstring of `"),
            pl.col("name"),
            pl.lit("` carries a heading or a label where this project writes plain lines"),
        ),
        measurements,
        predicate=pl.col("invalid_body"),
        finding_order=pl.lit(1),
        question=pl.concat_str(
            pl.lit("drop the headings from `"),
            pl.col("name"),
            pl.lit("` and write `name` and its description on one line"),
        ),
    )
    findings = FindingQuery(
        rows=pl.concat(
            [summary_findings.rows, body_findings.rows],
            how="vertical",
        ).sort("fact_id", "finding_order")
    )
    return RuleQuery.boolean(
        enriched,
        value,
        findings=findings,
    )
