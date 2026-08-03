from typing import TYPE_CHECKING, cast

from hypothesis import find, given, settings
from hypothesis import strategies as st

from mcmr.facts import (
    ClassFact,
    MemberDeclaration,
    OverrideFact,
    ParameterDeclaration,
    SourceSpan,
    SyntaxFact,
)
from mcmr.rules.general import (
    ancestor_count,
    class_method_order,
    initializer_called_on_a_stranger,
    overriding_method_demands_an_argument_the_base_defaulted,
    overriding_method_renames_a_parameter,
)
from mcmr.table import AnalysisSession, Table

from ...support import facts_of

if TYPE_CHECKING:
    from pathlib import Path

    from mcmr.facts import Fact

from .support import (
    assert_table_findings,
    families,
    is_inside,
    ordered,
    queried,
    readers,
    retained,
    reversed_records,
    scalar,
)


@given(data=st.data())
@settings(max_examples=50, deadline=None)
def test_every_generic_rule_answers_inside_its_contract_from_an_in_memory_table(
    data: st.DataObject,
) -> None:
    """A generic rule is total over its fact family and stays inside its contract.

    Coverage says a line ran. This says the value that line produced was one the catalog promised,
    over facts nobody wrote down by hand: every field takes the domain its own annotation states,
    so a family that grows a field is explored the run after a provider declares it.

    Three claims travel together because they need the same fact. A rule answers rather than
    raising, it answers the same thing twice so nothing leaks between invocations, and the answer
    is a Boolean, a count that never went negative, a percentage inside its own scale, or a member
    of the closed set the rule named.
    """
    for family in families():
        subject = data.draw(facts_of(family), label=family.__name__)
        table = retained(subject)
        for rule, definition in readers()[family]:
            value = scalar(queried(rule, table))
            again = scalar(queried(rule, table))

            assert again == value, f"{definition.id} answered twice and disagreed with itself"
            assert is_inside(value, definition), (
                f"{definition.id} declares {definition.output} and answered {value!r}"
            )


@given(data=st.data())
@settings(max_examples=50, deadline=None)
def test_a_generic_rule_reads_records_rather_than_their_retained_order(
    data: st.DataObject,
) -> None:
    """A fact states a set of records and a list is only how they were carried.

    Nothing promises a provider the order it discovered files, symbols, or edges in, so a rule
    reading the first record, sorting by nothing, or folding a set into a list has written an
    answer that moves when the kernel changes its traversal. Reversing every list the fact holds,
    all the way down through the records inside records, is the cheapest transformation that must
    not matter, and the two rules it is allowed to matter for say why in the ledger.
    """

    def verify(subject: Fact, family: type[Fact], *, flipped: Fact) -> None:
        selected = (pair for pair in readers()[family] if pair[1].id not in ordered())
        for rule, definition in selected:
            stated = scalar(queried(rule, retained(subject)))
            reversed_answer = scalar(queried(rule, retained(flipped)))
            assert stated == reversed_answer, (
                f"{definition.id} answered {stated!r} and then {reversed_answer!r} for the same "
                f"records in the opposite order"
            )

    for family in families():
        subject = data.draw(facts_of(family), label=family.__name__)
        flipped = reversed_records(subject)
        if flipped != subject:
            verify(subject, family, flipped=flipped)


@given(data=st.data())
@settings(max_examples=50, deadline=None)
def test_every_generic_rule_states_table_findings_that_agree_with_its_value(
    data: st.DataObject,
) -> None:
    """The evidence beside a value has to be about that value, for any fact at all.

    `tests/engine/test_rule_findings.py` proves each migrated rule says the right
    sentence about one written project. This proves the shape holds everywhere.
    An occurrence names its finding or denies the defect, every measurement is a
    real number on the scale it declares, and a rule that already ships a default
    fix leaves the repair to it rather than offering a second one.
    """
    for family in families():
        subject = data.draw(facts_of(family), label=family.__name__)
        table = retained(subject)
        for rule, definition in readers()[family]:
            assert_table_findings(queried(rule, table), definition)


def test_the_ledgers_name_exactly_the_rules_table_order_can_still_catch_out(
    tmp_path: Path,
) -> None:
    """Every order-sensitive rule is held by the fact that excuses it, so no ledger can rot.

    A ledger that only ever grew would be an allowance nobody reads. Each entry here carries the
    witness that proves it. `ORDERED` names a position that is genuinely meaningful instead of
    quietly excluding its readers from the property above.
    """

    def cases() -> tuple[
        OverrideFact, OverrideFact, OverrideFact, OverrideFact, OverrideFact, OverrideFact
    ]:
        """Build the two order-sensitive link pairs and their source fixtures."""
        link = OverrideFact(
            key="override:shop.Report",
            span=SourceSpan(path="shop/records.py"),
            derived="shop.Report",
            base="shop.Record",
            depth=1,
            base_names=["Record", "Row"],
            ancestor_names=["Record", "Row"],
            initializer_calls=["Stranger"],
        )
        transposed = link.model_copy(update={"base_names": ["Row", "Record"]})
        (tmp_path / "ordered.py").write_text(
            "class Receipt:\n    def open(self): ...\n    def save(self): ...\n",
            encoding="utf-8",
        )
        (tmp_path / "reversed.py").write_text(
            "class Receipt:\n    def save(self): ...\n    def open(self): ...\n",
            encoding="utf-8",
        )
        renamed_signature = OverrideFact(
            key="override:shop.Report",
            span=SourceSpan(path="shop/report.py"),
            declared=[
                MemberDeclaration(
                    name="send",
                    decorators=["classmethod"],
                    parameters=[
                        ParameterDeclaration(name="cls"),
                        ParameterDeclaration(name="payload"),
                        ParameterDeclaration(name="wait"),
                    ],
                )
            ],
            inherited=[
                MemberDeclaration(
                    name="send",
                    decorators=["classmethod"],
                    parameters=[
                        ParameterDeclaration(name="cls"),
                        ParameterDeclaration(name="payload"),
                        ParameterDeclaration(name="timeout"),
                    ],
                )
            ],
        )
        defaulted_signature = OverrideFact(
            key="override:shop.Report",
            span=SourceSpan(path="shop/report.py"),
            declared=[
                MemberDeclaration(
                    name="send",
                    decorators=["classmethod"],
                    parameters=[
                        ParameterDeclaration(name="klass"),
                        ParameterDeclaration(name="payload"),
                        ParameterDeclaration(name="timeout"),
                    ],
                )
            ],
            inherited=[
                MemberDeclaration(
                    name="send",
                    decorators=["classmethod"],
                    parameters=[
                        ParameterDeclaration(name="cls"),
                        ParameterDeclaration(name="payload"),
                        ParameterDeclaration(name="timeout", has_default=True),
                    ],
                )
            ],
        )
        reversed_renamed_signature = reversed_records(renamed_signature)
        reversed_defaulted_signature = reversed_records(defaulted_signature)

        return (
            link,
            transposed,
            renamed_signature,
            defaulted_signature,
            reversed_renamed_signature,
            reversed_defaulted_signature,
        )

    (
        link,
        transposed,
        renamed_signature,
        defaulted_signature,
        reversed_renamed_signature,
        reversed_defaulted_signature,
    ) = cases()

    assert (set(ordered()), all(ordered().values())) == (
        {"ALL-CLAS0001", "ALL-CLAS0005", "ALL-OVER0002", "ALL-OVER0003", "ALL-OVER0007"},
        True,
    )
    class_rows = (
        queried(
            class_method_order,
            cast(
                "Table[Fact]",
                AnalysisSession(tmp_path, typed_families=(ClassFact.__name__,)).class_tables(),
            ),
        )
        .values.collect()
        .rows(named=True)
    )
    class_answers = {str(row["path"]): int(row["integer_value"]) for row in class_rows}
    assert class_answers == {"ordered.py": 0, "reversed.py": 1}
    assert (
        scalar(queried(ancestor_count, retained(link))),
        scalar(queried(ancestor_count, retained(transposed))),
    ) == (2, 0)
    assert (
        scalar(queried(overriding_method_renames_a_parameter, retained(renamed_signature))),
        scalar(
            queried(
                overriding_method_renames_a_parameter,
                retained(reversed_renamed_signature),
            )
        ),
    ) == (1, 0)
    assert (
        scalar(
            queried(
                overriding_method_demands_an_argument_the_base_defaulted,
                retained(defaulted_signature),
            )
        ),
        scalar(
            queried(
                overriding_method_demands_an_argument_the_base_defaulted,
                retained(reversed_defaulted_signature),
            )
        ),
    ) == (1, 0)
    assert (
        scalar(queried(initializer_called_on_a_stranger, retained(link))),
        scalar(queried(initializer_called_on_a_stranger, retained(transposed))),
    ) == (1, 0), "this rule no longer reads the base its link names"


def test_the_schema_sweep_has_no_private_recursive_depth_ceiling() -> None:
    """A recursive fact reaches past the old two-layer cutoff without widening every example."""
    subject = find(
        facts_of(SyntaxFact),
        lambda fact: fact.tree is not None and fact.tree.depth > 2,
    )

    assert subject.tree is not None
    assert subject.tree.depth > 2
