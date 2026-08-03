from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ..... import Category, rule
from .....domain.contracts import Criterion
from .....execution import ClassificationBackend, CriterionValue
from .....execution.queries import AssessmentContract, ModelQuery
from .....facts import StringExpressionFact
from .....table import GenericRelation, Table


class _StringConstructionMechanism(StrEnum):
    LITERAL = auto()
    F_STRING = auto()
    STRING_TEMPLATE = auto()
    JINJA2 = auto()
    JOIN = auto()
    F_STRING_JOIN = auto()
    UNCERTAIN = auto()


_CRITERIA = (
    Criterion(
        name="local expressions",
        question="Does Python own runtime expressions inserted into the text?",
    ),
    Criterion(name="python iteration", question="Does Python own iteration over rendered items?"),
    Criterion(
        name="external placeholders",
        question="Do nonprogrammers or external data own simple placeholders?",
    ),
    Criterion(
        name="template semantics",
        question="Does the text need template control flow or contextual escaping?",
    ),
)
_TABLE = (
    (_StringConstructionMechanism.JINJA2, (("template semantics", CriterionValue.YES),)),
    (
        _StringConstructionMechanism.F_STRING_JOIN,
        (("local expressions", CriterionValue.YES), ("python iteration", CriterionValue.YES)),
    ),
    (_StringConstructionMechanism.JOIN, (("python iteration", CriterionValue.YES),)),
    (
        _StringConstructionMechanism.STRING_TEMPLATE,
        (("external placeholders", CriterionValue.YES),),
    ),
    (_StringConstructionMechanism.F_STRING, (("local expressions", CriterionValue.YES),)),
)


@rule(
    "ALL-STRI1001",
    policy=Category.outcomes(
        _StringConstructionMechanism, neutral=set(_StringConstructionMechanism)
    ),
)
def string_construction_mechanism(
    subject: Table[StringExpressionFact],
    backend: ClassificationBackend,
    *,
    minimum_characters: PositiveInt = 80,
) -> ModelQuery[_StringConstructionMechanism]:
    """Select a string mechanism from explicit construction requirements.

    Definition
    ----------
    Ask the selected judgment backend for four independently cited construction facts and reduce
    them through a fixed decision table. The model identifies requirements but never chooses the
    mechanism. Literals own static text, f-strings own local expressions, `str.join` owns Python
    iterables, `string.Template` owns simple external placeholders, and Jinja2 owns template logic
    or contextual markup escaping.
    `minimum_characters` limits contextual judgment to substantial string expressions.

    Evidence
    --------
    The frozen bundle cites the string boundary, its authors, dynamic values, iteration ownership,
    control flow, and escaping requirements. Missing, duplicate, conflicting, or uncited answers
    remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    SQL, shell, regular-expression, logging, localization, and security-sensitive APIs retain
    their own parameterization contracts. Ruff UP031, UP032, FLY002, and ISC003 plus Pylint R1713
    retain direct syntax diagnostics.

    Examples
    --------
    `f"Hello {user.name}"` is an `f_string`. Rendering rows in Python and joining them is
    `f_string_join`. An HTML email with template loops and escaping is `jinja2`.

    References
    ----------
    Cites "PEP 498, Literal String Interpolation"
    https://peps.python.org/pep-0498/
    Cites "The Python Standard Library", `string.Template`
    https://docs.python.org/3/library/string.html#template-strings
    Cites "Jinja documentation", template designer
    https://jinja.palletsprojects.com/en/stable/templates/
    Cites "PEP 8, Style Guide for Python Code", programming recommendations for `str.join`
    https://peps.python.org/pep-0008/#programming-recommendations
    """
    query = backend.assessment(
        subject,
        contract=AssessmentContract(
            criteria=list(_CRITERIA),
            instructions=string_construction_mechanism.instructions,
            decision_table=_TABLE,
            default=_StringConstructionMechanism.LITERAL,
            uncertain=_StringConstructionMechanism.UNCERTAIN,
        ),
    )
    record_columns = set(subject.lazy(GenericRelation.RECORDS).collect_schema().names())
    if not {"node.id", "runtime_value"}.issubset(record_columns):
        return query
    relations = subject
    facts = relations.facts().select("fact_order", "fact_id", "language")
    expressions = (
        relations.records("expressions")
        .filter(
            (pl.col("kind") == "literal")
            & (pl.col("runtime_value").str.len_chars() >= minimum_characters)
        )
        .join(facts, on=("fact_order", "fact_id"), how="inner")
        .with_columns(
            pl.col("record_id").alias("fact_id"),
            pl.col("node.span.path").alias("path"),
            pl.col("node.span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("node.span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("node.span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("node.span.end_column").cast(pl.UInt64).alias("end_column"),
        )
        .filter(~pl.col("path").str.contains(r"(?:^|/)tests?(?:/|$)"))
    )
    return query.project(
        expressions,
        fields=(
            "kind",
            "runtime_value",
            "literal_fragment_count",
            "wraps_single_runtime_line",
            "node.text",
        ),
    )
