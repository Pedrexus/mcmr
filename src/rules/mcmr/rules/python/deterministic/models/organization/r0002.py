import polars as pl

from ...... import rule
from ......domain.contracts import Unit
from ......facts import ClassFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ClassRelation, Table


@rule("PY-MODE0001")
def shared_model_file_shape(
    subject: Table[ClassFact],
) -> CountQuery:
    """Require one model-shaped class in each shared `models` package implementation file.

    Definition
    ----------
    Apply only to Python files below a `models` directory and exclude `__init__.py`. Require
    exactly one top-level class deriving a recognized Pydantic, house model, SQL table, or
    decorated dataclass foundation. A directory counts as a shared model package only when some
    file inside it really declares a data model, so a folder of neural networks named the same way
    is left alone. Enum classes belong in `enums`. Local model groups consumed only within one
    feature package may remain together in that feature's `models.py` instead.

    Evidence
    --------
    A finding lists every top-level class and covers the complete file. Empty utility files,
    multiple model classes, ordinary service classes, and enum classes all violate this shared
    package shape. The value is the number of files in the shared package that do not hold exactly
    one model class.

    Exceptions
    ----------
    `models/__init__.py` may export model classes used outside the package. A feature-local
    `enums.py` inside a nested model package remains governed by the enum placement rules. A rule
    family named `models` is not a shared data-model package. A class reaching a foundation only
    through a project-owned intermediate base is not counted, because the base each file names is
    what one parse can settle. Generated schemas and migration snapshots may be excluded by path.

    Examples
    --------
    Bad
    ~~~
    `models/accounts.py` defines `Account`, `Profile`, and `AccountStatus` together.

    Good
    ~~~~
    `models/account.py` defines only the `Account` Pydantic model. A final generic result model
    derived through a project-owned abstract `RuleResult` is also accepted. `models/__init__.py`
    exports public models when outside consumers need the package API.

    References
    ----------
    Cites "Pydantic documentation", models
    https://pydantic.dev/docs/validation/latest/concepts/models/
    Cites "The Python Standard Library", dataclasses
    https://docs.python.org/3/library/dataclasses.html
    Cites "A Philosophy of Software Design", chapters 4 and 5
    """
    facts = subject.lazy(ClassRelation.FACTS)
    evidence = (
        subject.lazy(ClassRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(ClassRelation.MODEL_FILES)
        .filter(
            ~pl.col("is_package_initializer")
            & ((pl.col("top_level_class_count") != 1) | (pl.col("model_class_count") != 1))
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
                pl.col("path"),
                pl.lit("` declares "),
                pl.col("top_level_class_count"),
                pl.lit(" top-level classes of which "),
                pl.col("model_class_count"),
                pl.lit(" are models"),
            ),
            (("shared model file shape", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
