import polars as pl
from pydantic import PositiveInt

from ...... import rule
from ......facts import TestCaseGroupFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ..cases.case_relations import TestCaseTables


@rule("PY-TEST0017")
def broad_example_property_candidate_count(
    subject: Table[TestCaseGroupFact],
    *,
    minimum_cases: PositiveInt = 10,
) -> CountQuery:
    """Count broad literal example families that should state one generated property.

    Definition
    ----------
    Find sibling tests with the same syntax after literals are replaced by typed slots. Require at
    least `minimum_cases` distinct literal vectors. A large homogeneous example family is evidence
    that the suite is enumerating a domain around one invariant, which Hypothesis can generate and
    shrink more directly. The default boundary is ten examples.

    Evidence
    --------
    Each finding reports the exact example count and literal-neutral test shape. The value is the
    number of broad example families. `PY-TEST0003` owns shorter families that should use ordinary
    Pytest parametrization.

    Exceptions
    ----------
    Repeated vectors, different control flow, fixtures, call targets, marks, or literal types form
    different groups or abstain. Keep explicit examples when every case has distinct domain
    meaning, marks, or identifiers. A property test must state an invariant rather than merely
    generating the old examples.

    Examples
    --------
    Bad
    ~~~
    Ten sibling `test_round_trip_*` tests differ only in one integer input, so the value is `1`.

    Good
    ~~~~
    Three named `test_protocol_*` scenarios state distinct behavior, so the value remains `0`.

    References
    ----------
    Cites "Hypothesis documentation", when to use property-based testing
    https://hypothesis.readthedocs.io/en/latest/tutorial/introduction.html#when-to-use-hypothesis-and-property-based-testing
    Cites "pytest documentation", parametrization
    https://docs.pytest.org/en/stable/how-to/parametrize.html
    """
    relations = TestCaseTables(subject)
    selected = (
        relations.groups()
        .join(relations.vector_counts(), on="record_id", how="left")
        .with_columns(pl.col("vector_count", "distinct_vector_count").fill_null(0))
        .filter(
            (pl.col("vector_count") >= minimum_cases)
            & (pl.col("vector_count") == pl.col("distinct_vector_count"))
        )
    )
    frame = relations.counted(selected)
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        pl.lit(1, dtype=pl.UInt64),
        findings=FindingQuery.precise_integer(
            frame,
            pl.col("value"),
            "broad example property candidate count",
            evidence=pl.col("evidence"),
        ),
    )
