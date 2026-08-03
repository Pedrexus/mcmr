import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-MODE0003")
def approved_model_foundation(
    subject: Table[ClassFact],
) -> CountQuery:
    """Require direct Pydantic models to use an established approved house base.

    Definition
    ----------
    First establish project policy by finding at least one module anywhere in the repository that
    imports a foundation from `patos` or from a `common.bases` module. Then inspect project-owned
    top-level classes and report direct subclasses of an imported `pydantic.BaseModel` that do not
    also inherit an approved base. Resolve direct imports, module imports, and aliases through the
    bindings each file states. Each bypassing class contributes one to the result.

    Evidence
    --------
    Each finding identifies the direct model class and its source range. Which foundations count
    as approved is the provider's single project-specific input, and it recognizes the two house
    homes for one. The value is the number of classes deriving `pydantic.BaseModel` without an
    approved foundation.

    Exceptions
    ----------
    Abstain when the project has not established a house foundation. Ignore Pydantic dataclasses,
    `RootModel`, dynamic `create_model` calls, unresolved bases, nested classes, and subclasses of
    a project foundation because their Pydantic ancestry is not locally proven. The repository's
    Git ignore files decide whether generated and vendored sources are in the scan, and per-rule
    globs can narrow it further.

    Examples
    --------
    Bad
    ~~~
    After `from patos import FrozenModel` establishes the policy, this direct foundation bypasses
    it.

    .. code-block:: python

       from pydantic import BaseModel

       class User(BaseModel):
           name: str

    Good
    ~~~~
    The project-owned foundation makes mutability and validation policy explicit.

    .. code-block:: python

       from patos import FrozenModel

       class User(FrozenModel):
           name: str

    References
    ----------
    Cites "Pydantic documentation", models
    https://docs.pydantic.dev/latest/concepts/models/
    Cites "Pydantic documentation", custom base model guidance
    https://docs.pydantic.dev/latest/concepts/models/#custom-base-classes
    Cites "PEP 8, Style Guide for Python Code", public and internal interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    """
    facts = subject.lazy(ClassRelation.FACTS)
    policies = facts.select("fact_id", "has_approved_model_foundation_policy")
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.CLASSES)
        .join(policies, on="fact_id", how="inner")
        .filter(
            pl.col("has_approved_model_foundation_policy")
            & pl.col("directly_inherits_pydantic_base_model")
            & ~pl.col("inherits_approved_model_foundation")
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` inherits Pydantic directly instead of the approved model foundation"),
            ),
            (("approved model foundation", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
