from typing import cast

from mcmr.facts import (
    SourceSpan,
    SymbolReach,
)
from mcmr.rules.general import (
    ancestor_count,
    boolean_parameter_count,
    declared_field_count,
    module_inception,
    public_method_count,
)
from mcmr.table import FunctionRelation

from .support import (
    attribute,
    class_table,
    class_values,
    function_table,
    function_values,
    link,
    module,
    native_query,
    reach,
    retained_value,
)


def test_public_method_count_reads_the_widest_type_in_the_module() -> None:
    subject = class_table(
        {
            "wide.py": """class Session:
    host = None

    def __init__(self): pass
    def open(self): pass
    def read(self): pass
    def close(self): pass
    def __repr__(self): pass
    def _reset(self): pass
    def __cache(self): pass


class Row:
    @property
    def value(self): return None
""",
            "narrow.py": "class Row:\n    @property\n    def value(self): return None\n",
            "empty.py": "value = 1\n",
        }
    )
    answers = class_values(
        native_query(public_method_count, subject),
        subject,
    )

    assert answers == {"empty.py": 0, "narrow.py": 0, "wide.py": 3}


def test_declared_field_count_groups_members_under_the_type_declaring_them() -> None:
    subject = reach(
        attribute("service.Session.host"),
        attribute("service.Session.port"),
        attribute("service.Session.timeout"),
        attribute("service.Row.value"),
        SymbolReach(
            qualname="service.Session.open",
            kind="method",
            span=SourceSpan(path="src/service.py"),
        ),
        SymbolReach(
            qualname="service.LIMIT",
            kind="variable",
            span=SourceSpan(path="src/service.py"),
            is_module_scope=True,
        ),
    )

    assert retained_value(subject, declared_field_count) == 3
    assert retained_value(reach(attribute("service.Row.value")), declared_field_count) == 1
    assert retained_value(reach(), declared_field_count) == 0


def test_ancestor_count_reports_once_at_the_first_declared_base() -> None:
    primary = link(
        "service.Report",
        base="service.Record",
        base_names=["Record"],
        ancestor_names=["Record", "Row"],
    )

    assert retained_value(primary, ancestor_count) == 2
    assert retained_value(primary.model_copy(update={"depth": 2}), ancestor_count) == 0
    assert retained_value(primary.model_copy(update={"base": "service.Row"}), ancestor_count) == 0
    assert retained_value(primary.model_copy(update={"base_names": []}), ancestor_count) == 0


def test_boolean_parameter_count_reads_every_flag_whatever_its_position() -> None:
    subject = function_table(
        {
            "src/service.py": """class Renderer:
    def render(self, document: Document, inline: bool, *, minified: bool, strict=False):
        pass


def empty():
    pass


def single(inline: bool):
    pass
"""
        }
    )
    answer = native_query(boolean_parameter_count, subject)
    answers = function_values(answer, subject)
    functions = subject.frame(FunctionRelation.FUNCTIONS)
    render_id, single_id = (
        functions.filter(name="render").item(0, "fact_id"),
        functions.filter(name="single").item(0, "fact_id"),
    )
    if answer.findings is None:
        raise TypeError("the Boolean parameter rule emitted no findings relation")
    all_findings = answer.findings.rows.collect()
    findings, single_finding = (
        all_findings.filter(all_findings["fact_id"] == render_id),
        all_findings.filter(all_findings["fact_id"] == single_id),
    )
    assert (
        answers["render"],
        answers["empty"],
        answers["single"],
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
            "reduce the state space of `render`"
        ),
        cast("str", single_finding.item(0, "message")).startswith(
            "`single` takes 1 Boolean parameter, which creates 2"
        ),
    ) == (
        3,
        0,
        1,
        "`render` takes 3 Boolean parameters, which create 8 behavior combinations, with "
        "`inline` as `bool`, `minified` as `bool`, `strict` with a Boolean default",
        "src/service.py",
        {
            "Boolean parameters": 3,
            "possible behavior combinations": 8,
            "parameters declared": 5,
        },
        True,
        True,
    )


def test_module_inception_reports_only_an_exact_repetition() -> None:
    assert retained_value(module("src/parser/parser.py"), module_inception) is True
    assert retained_value(module("crates/parser/parser.rs"), module_inception) is True
    assert retained_value(module("src/parser/lexer.py"), module_inception) is False
    assert retained_value(module("src/parser/__init__.py"), module_inception) is False
    assert retained_value(module("src/parser/mod.rs"), module_inception) is False
    assert retained_value(module("src/parser/parser_table.py"), module_inception) is False
