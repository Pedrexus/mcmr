import polars as pl
from pydantic import PositiveInt

from ..... import Category, rule
from .....domain.primitives import NonEmptyStr
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ProseSegmentFact
from .....table import GenericRelation, Table
from .contracts import ProseLanguage


@rule(
    "ALL-WRIT1002",
    policy=Category.outcomes(
        ProseLanguage,
        good={ProseLanguage.TARGET},
        neutral={ProseLanguage.UNCERTAIN},
    ),
)
def docstring_language(
    subject: Table[ProseSegmentFact],
    backend: ClassificationBackend,
    *,
    target_language: NonEmptyStr = "American English",
    minimum_characters: PositiveInt = 24,
) -> ModelQuery[ProseLanguage]:
    """Keep source docstrings in one configured project language.

    Definition
    ----------
    Classify each substantial docstring as `target`, `other`, or `uncertain`. The configured target
    is `target_language`, which defaults to American English. Judge only the docstring text. Do not
    guess from short fragments, code blocks, identifiers, protocol words, or proper names.

    Evidence
    --------
    Each finding cites the exact declaration range, docstring text, model confidence, and model
    provenance. `minimum_characters` excludes fragments that language identification models cannot
    distinguish reliably.

    Exceptions
    ----------
    Quoted user text and required foreign terms can remain when the surrounding explanation uses
    the project language. Configure another target for a repository whose readers use it.

    Examples
    --------
    With the default target, `Return the decoded payload.` is `target`. A substantial Portuguese
    explanation is `other`. `HTTP client.` is excluded by the length floor.

    References
    ----------
    Cites "GlotLID", model guidance on confidence and short text
    https://github.com/cisnlp/GlotLID
    Cites "Lingua", language detection for short and mixed-language text
    https://github.com/pemistahl/lingua-py
    """
    instructions = (
        f"{docstring_language.instructions}\n\n"
        f"The configured target language is {target_language}."
    )
    query = backend.classification(
        subject,
        category=ProseLanguage,
        instructions=instructions,
    )
    record_columns = set(subject.lazy(GenericRelation.RECORDS).collect_schema().names())
    if not {"character_count", "text", "token_count"}.issubset(record_columns):
        return query
    facts = subject.facts().select(
        pl.col("fact_id").alias("module_fact_id"),
        "language",
        pl.col("path").alias("module_path"),
        pl.col("start_line").alias("module_start_line"),
        pl.col("start_column").alias("module_start_column"),
        pl.col("end_line").alias("module_end_line"),
        pl.col("end_column").alias("module_end_column"),
    )
    sections = (
        subject.records("sections")
        .filter(pl.col("character_count") >= minimum_characters)
        .join(facts, left_on="fact_id", right_on="module_fact_id", how="inner")
        .select(
            "fact_order",
            pl.col("record_id").alias("fact_id"),
            pl.coalesce("node.span.path", "module_path").alias("path"),
            pl.coalesce("node.span.start_line", "module_start_line")
            .cast(pl.UInt64)
            .alias("start_line"),
            pl.coalesce("node.span.start_column", "module_start_column")
            .cast(pl.UInt64)
            .alias("start_column"),
            pl.coalesce("node.span.end_line", "module_end_line").cast(pl.UInt64).alias("end_line"),
            pl.coalesce("node.span.end_column", "module_end_column")
            .cast(pl.UInt64)
            .alias("end_column"),
            "language",
            "text",
            "character_count",
            "token_count",
        )
    )
    return query.project(sections, fields=("text", "character_count", "token_count"))
