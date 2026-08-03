from pathlib import Path
from typing import cast

from mcmr.domain.contracts import RuleValue
from mcmr.facts import FunctionFact, SourceSpan
from mcmr.query import RuleQuery, scalar_row_value
from mcmr.rules.general import positional_boolean_parameter
from mcmr.table import AnalysisSession, FunctionRelation, Table

from ..support import written

_SPAN = SourceSpan(path="src/loader.py")


def function_table(root: Path, sources: dict[str, str]) -> Table[FunctionFact]:
    """Parse one source corpus into specialized native function relations."""
    return AnalysisSession(
        written(root, sources),
        suffixes=sorted({Path(name).suffix for name in sources}),
        typed_families=(FunctionFact.__name__,),
    ).function_tables()


def function_values(result: RuleQuery, subject: Table[FunctionFact]) -> dict[str, RuleValue]:
    """Return every function answer by its source-level name."""
    functions = subject.frame(FunctionRelation.FUNCTIONS).select("fact_id", "name")
    rows = result.values.collect().join(functions, on="fact_id")
    return {cast("str", row["name"]): scalar_row_value(row) for row in rows.iter_rows(named=True)}


def test_a_positional_boolean_reads_as_nothing_at_the_call_site(tmp_path: Path) -> None:
    """A positional Boolean says nothing about what is true in any language."""
    subject = function_table(
        tmp_path,
        {
            "src/loader.py": """def render(document, inline: bool, minified: bool):
    pass


def named(document, *, inline: bool):
    pass
""",
            "src/service.rs": """struct Service;
impl Service {
    fn rust(&self, inline: bool) {}
}
""",
        },
    )
    answer = positional_boolean_parameter.invoke_table(subject, settings={}, dependencies={})
    assert isinstance(answer, RuleQuery)
    answers = function_values(answer, subject)
    render_id = subject.frame(FunctionRelation.FUNCTIONS).filter(name="render").item(0, "fact_id")
    assert answer.findings is not None
    rows = answer.findings.rows.collect()
    findings = rows.filter(rows["fact_id"] == render_id)

    assert (
        answers["render"],
        answers["named"],
        answers["rust"],
        findings.item(0, "message"),
        findings.item(0, "path"),
        dict(
            zip(
                findings.item(0, "measurement_names"),
                findings.item(0, "measurement_values"),
                strict=True,
            )
        ),
        cast("str", findings.item(0, "choice_question")).startswith(
            "make `inline` say what its Boolean value means"
        ),
    ) == (
        2,
        0,
        1,
        "`render` takes Boolean parameter `inline` in position 2, where a call passes its value "
        "without its name",
        _SPAN.path,
        {
            "position in the parameter list": 2,
            "Boolean parameters passed by position": 2,
        },
        True,
    )
