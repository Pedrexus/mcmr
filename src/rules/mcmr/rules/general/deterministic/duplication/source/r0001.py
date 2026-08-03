import polars as pl

from ...... import rule
from ......facts import MethodGroupFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table


@rule("ALL-DUPL0001")
def repeated_class_method_count(
    subject: Table[MethodGroupFact],
) -> CountQuery:
    """Count exact sibling methods that can be pulled into their shared direct base.

    Definition
    ----------
    Parse the configured project sources and compare methods declared directly in classes sharing
    one meaningful direct base. Normalize each complete method abstract syntax tree by removing
    its leading docstring and source positions. Names, signatures, decorators, annotations, and
    executable statements must still match exactly. The value counts definitions beyond the first
    stable path and line in every qualified group. Module functions, nested functions, and classes
    without a shared ownership boundary are not compared.

    Evidence
    --------
    Every extra definition receives a finding at its own location. Each finding cites every
    definition in the group, including the first, and measures affected definitions and files.
    Every reported group already has one shared direct base, so the finding identifies that
    concrete pull-up boundary rather than proposing a speculative new abstraction. The value is the
    number of definitions past the first in every qualified group.

    Exceptions
    ----------
    Docstring-only bodies, `pass`, ellipsis, `raise NotImplementedError`, and
    `return NotImplemented` are placeholders rather than duplicated implementations. Unrelated
    classes are excluded because an extraction owner cannot be proven deterministically. Provider
    selection decides whether tests and vendored paths are in scope because thin adapters and
    protocol doubles often repeat intentionally. Comments and formatting are absent from Python
    syntax trees. Similar methods with different names,
    signatures, decorators, annotations, or statements remain separate.

    Examples
    --------
    Bad
    ~~~
    `PromptCategory.key` and `JudgmentCriterion.key` both use `@property`, accept only `self`, and
    return `normalize_name(self.name)`. Different human docstrings do not hide the repeated
    implementation. If both classes directly inherit `KeyedStrEnum`, the finding can suggest
    moving the shared contract there.

    Good
    ~~~~
    Two protocol methods whose bodies are `...` are ignored. Two unrelated analyzer `result`
    methods and two identical test-backend properties are also ignored because neither establishes
    a production pull-up boundary.

    References
    ----------
    Cites "Refactoring", Pull Up Method
    https://refactoring.com/catalog/pullUpMethod.html
    Cites "The Python Standard Library", `ast`, abstract syntax trees
    https://docs.python.org/3/library/ast.html
    Cites "The Python Standard Library", `ast.get_docstring`
    https://docs.python.org/3/library/ast.html#ast.get_docstring
    """
    relations = subject
    locations = (
        relations.values("groups.locations")
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(pl.col("string_value").n_unique().alias("locations"))
    )
    groups = (
        relations.records("groups")
        .filter(pl.col("direct_base") != "")
        .join(
            locations,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        )
        .with_columns(pl.col("locations").fill_null(0))
        .with_columns((pl.col("locations") - 1).clip(lower_bound=0).alias("duplicates"))
    )
    facts = relations.counted(groups, pl.col("duplicates"))
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "repeated class method count",
            evidence=pl.col("evidence"),
        ),
    )
