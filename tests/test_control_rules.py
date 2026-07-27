from mcmr.facts import SourceSpan, SyntaxFact, SyntaxNode
from mcmr.rules.general.deterministic.control.r0001 import superfluous_else_after_jump
from mcmr.rules.general.deterministic.control.r0002 import statement_without_effect
from mcmr.rules.general.deterministic.control.r0003 import debug_artifact_left_behind
from mcmr.rules.general.deterministic.control.r0004 import deeply_nested_body
from tests.conftest import Declaration

PATH = "src/orders.py"
DECLARED = Declaration(path=PATH, qualname="settle", source="def settle(values): ...")
OPENING = DECLARED.span


def at(line: int, *, column: int = 8, ends: int = 0) -> SourceSpan:
    """Locate one node on the lines and the column it was written at."""
    return SourceSpan(path=PATH, start_line=line, start_column=column, end_line=ends or line)


def branch(text: str, *children: SyntaxNode, line: int = 2, column: int = 4) -> SyntaxNode:
    """Build one branch spanning the lines of its own source, indentation included."""
    ends = line + len(text.splitlines()) - 1
    return SyntaxNode(
        kind="branch",
        text=text,
        span=at(line, column=column, ends=ends),
        children=list(children),
    )


def statement(kind: str, text: str, *, line: int, column: int = 8) -> SyntaxNode:
    """Build one statement of the given kind on one line."""
    return SyntaxNode(kind=kind, text=text, span=at(line, column=column))


def jumping_branch(last: SyntaxNode) -> SyntaxFact:
    """Build `if not values` followed by an else, with `last` closing the first block."""
    text = f"if not values:\n        {last.text}\n    else:\n        return total"
    return DECLARED.of(
        branch(
            text,
            statement("operation", "not values", line=2, column=7),
            last,
            statement("return", "return total", line=5),
        ),
        span=OPENING,
    )


def effect(child: SyntaxNode | None = None) -> SyntaxFact:
    """Build one declaration whose body is a single expression statement."""
    held = SyntaxNode(kind="effect", text="order.total == 0", span=at(2))
    return DECLARED.of(
        held if child is None else held.model_copy(update={"children": [child]}), span=OPENING
    )


def nested(*kinds: str) -> SyntaxFact:
    """Build one declaration nesting the given kinds, each written deeper than the one above it."""
    node = SyntaxNode(kind="call", name="charge", text="charge(item)", span=at(9, column=40))
    for level, kind in reversed(list(enumerate(kinds))):
        node = SyntaxNode(
            kind=kind,
            text=kind,
            span=at(2 + level, column=4 + 4 * level, ends=16 - level),
            children=[node],
        )
    return DECLARED.of(node, span=OPENING)


def chain(*lines: int) -> SyntaxFact:
    """Build the arms of one `} else if {` chain, every arm closing where the first one closes."""
    node = SyntaxNode(kind="scope", text="} else {", span=at(587, column=11, ends=589))
    for line in lines:
        node = SyntaxNode(
            kind="branch",
            text="} else if {",
            span=at(line, column=11, ends=589),
            children=[node],
        )
    return DECLARED.of(
        SyntaxNode(
            kind="branch",
            text='if name == "__init__" {',
            span=at(573, column=15, ends=589),
            children=[node],
        ),
        span=OPENING,
    )


def test_an_else_is_reported_only_where_a_jump_closed_the_block_above_it() -> None:
    """The statement closing the first block is what decides whether the else earns its level.

    A jump already ended the block, so the else only buys a level of indentation. After ordinary
    work the else is the only thing saying the two blocks exclude each other, and that holds for a
    binding a reader cannot even parse at a glance. `returned = 1` merely starts like a jump, which
    is why the first word is read whole, and a jump with nothing after it is the shape this rule
    asks for rather than the one it reports.
    """
    jumped = jumping_branch(statement("return", "return 0", line=3))
    kept = jumping_branch(statement("binding", "total = 0", line=3))
    unreadable = jumping_branch(statement("binding", "(total, extra) = split(row)", line=3))
    named = jumping_branch(statement("binding", "returned = 1", line=3))
    alone = DECLARED.of(
        branch(
            "if not values:\n        return 0",
            statement("operation", "not values", line=2, column=7),
            statement("return", "return 0", line=3),
        ),
        span=OPENING,
    )

    assert superfluous_else_after_jump(jumped) == 1
    assert superfluous_else_after_jump(kept) == 0
    assert superfluous_else_after_jump(unreadable) == 0
    assert superfluous_else_after_jump(named) == 0
    assert superfluous_else_after_jump(alone) == 0


def test_an_else_is_charged_to_the_branch_it_is_written_level_with() -> None:
    """Indentation is what names the branch an alternative belongs to, in either spelling.

    Reading the indentation keeps an outer branch from paying for an inner else, and `} else {`
    closing on `panic!` is the Rust spelling of the shape Python writes with a dedent, which the
    `jumps` setting is what a project narrows.
    """
    inner = branch(
        "if order.is_paid:\n            return 0\n        else:\n            return 1",
        statement("name", "order.is_paid", line=3, column=11),
        statement("return", "return 0", line=4, column=12),
        statement("return", "return 1", line=6, column=12),
        line=3,
        column=8,
    )
    outer = branch(
        "if order.is_open:\n        if order.is_paid:\n            return 0"
        "\n        else:\n            return 1",
        statement("name", "order.is_open", line=2, column=7),
        inner,
    )
    braced = DECLARED.of(
        branch(
            'if values.is_empty() {\n        panic!("empty");\n    } else {'
            "\n        return total;\n    }",
            statement("call", "values.is_empty()", line=2, column=7),
            SyntaxNode(kind="effect", text='        panic!("empty");', span=at(3)),
            statement("return", "return total;", line=5),
        ),
        span=OPENING,
    )

    assert superfluous_else_after_jump(DECLARED.of(outer, span=OPENING)) == 1
    assert superfluous_else_after_jump(braced) == 1
    assert superfluous_else_after_jump(braced, jumps=("return",)) == 0


def test_a_branch_a_frontend_left_bare_is_read_from_its_own_source() -> None:
    """What a frontend did not state is recovered from the branch text, or not judged at all.

    The Rust frontend stops at the branch, so the block it holds is only in the text, where a jump
    at the indentation the block opened with counts and one buried in a nested body or missing
    entirely does not. A branch carrying no span locates no else, so the rule declines rather than
    guesses.
    """
    jumping = DECLARED.of(
        branch(
            'if values.is_empty() {\n        panic!("empty");\n    } else {'
            "\n        return total;\n    }"
        ),
        span=OPENING,
    )
    looping = DECLARED.of(
        branch(
            "if values.is_empty() {\n        for value in values {"
            "\n            return *value;\n        }\n    } else {\n        work();\n    }"
        ),
        span=OPENING,
    )
    empty = DECLARED.of(
        branch("if values.is_empty() {\n    } else {\n        work();\n    }"), span=OPENING
    )
    unplaced = DECLARED.of(
        SyntaxNode(kind="branch", text="if not values:\n    return 0\nelse:\n    return total"),
        span=OPENING,
    )

    assert superfluous_else_after_jump(jumping) == 1
    assert superfluous_else_after_jump(looping) == 0
    assert superfluous_else_after_jump(empty) == 0
    assert superfluous_else_after_jump(unplaced) == 0


def test_a_statement_is_inert_only_where_its_whole_value_can_do_no_work() -> None:
    """A line that computes and discards is reported, and every kind that works is not.

    The line runs and nothing happens, which is usually an assert that lost its keyword, and
    `inert_kinds` is what a project restates when its language spells the kinds differently. A call
    may do all its work through a side effect and a lone string documents the code, `local[head]`
    raises when the program is missing, which is the whole point of the line, and `command & FG`
    runs a program while `first >> second` wires a pipeline.
    """
    computed = effect(SyntaxNode(kind="operation", text="order.total == 0", span=at(2)))
    bare = effect(SyntaxNode(kind="member", text="order.items", span=at(2)))
    negated = effect(SyntaxNode(kind="operation", text="not order.paid", span=at(2)))
    called = effect(SyntaxNode(kind="call", name="charge", text="charge(order)", span=at(2)))
    documented = effect(SyntaxNode(kind="text", text='"""Settle every order."""', span=at(2)))
    probing = effect(SyntaxNode(kind="index", text="local[head]", span=at(2)))
    ran = effect(
        SyntaxNode(kind="operation", text='remote["bash"][["-lc", script]] & FG', span=at(2))
    )
    wired = effect(SyntaxNode(kind="operation", text="extract >> transform >> load", span=at(2)))

    assert statement_without_effect(computed) == 1
    assert statement_without_effect(bare) == 1
    assert statement_without_effect(negated) == 1
    assert statement_without_effect(computed, inert_kinds=("literal",)) == 0
    assert statement_without_effect(called) == 0
    assert statement_without_effect(documented) == 0
    assert statement_without_effect(probing) == 0
    assert statement_without_effect(probing, inert_kinds=("index",)) == 1
    assert statement_without_effect(ran) == 0
    assert statement_without_effect(wired) == 0


def test_only_the_node_covering_the_whole_statement_answers_for_the_line() -> None:
    """An operand beneath a statement is never read as the statement itself.

    The `1` inside `exit(1)` is an argument and the line it sits on ends the program, and the same
    holds for the name inside a return. With nothing beneath it at all, which is what the depth
    bound leaves behind, the rule cannot say what the statement computed.
    """
    exiting = DECLARED.of(
        SyntaxNode(
            kind="effect",
            name="std::process::exit",
            text="    std::process::exit(1);",
            span=at(25, column=4),
            children=[SyntaxNode(kind="literal", text="1", span=at(25, column=23))],
        ),
        span=OPENING,
    )
    returning = DECLARED.of(
        SyntaxNode(
            kind="effect",
            text="        return None;",
            span=at(472, column=8),
            children=[SyntaxNode(kind="name", name="None", text="None", span=at(472, column=15))],
        ),
        span=OPENING,
    )

    assert statement_without_effect(exiting) == 0
    assert statement_without_effect(returning) == 0
    assert statement_without_effect(effect()) == 0


def test_a_debug_artifact_is_read_from_the_name_a_frontend_resolved_or_from_its_text() -> None:
    """A print and a breakpoint are reported, a logger is not, and a macro falls back to text.

    Both a print and a breakpoint follow the code into production, where one leaks output and the
    other hangs, and `artifacts` is what a project restates for its own console wrapper. A project
    that configured a logger already decided where its output goes, while Rust hands over
    `println!` with no resolved name, so the text is the only reading left.
    """
    subject = DECLARED.of(
        SyntaxNode(
            kind="effect",
            text="print(order.card)",
            span=at(2),
            children=[SyntaxNode(kind="call", name="print", text="print(order.card)")],
        ),
        SyntaxNode(kind="call", name="breakpoint", text="breakpoint()", span=at(3)),
        span=OPENING,
    )
    logged = DECLARED.of(
        SyntaxNode(kind="call", name="logger.debug", text="logger.debug(order)", span=at(2)),
        span=OPENING,
    )
    macro = DECLARED.of(
        SyntaxNode(kind="effect", text='        println!("{total}");', span=at(2)), span=OPENING
    )

    assert debug_artifact_left_behind(subject) == 2
    assert debug_artifact_left_behind(subject, artifacts=("dbg!",)) == 0
    assert debug_artifact_left_behind(logged) == 0
    assert debug_artifact_left_behind(macro) == 1


def test_a_test_file_and_a_command_line_entry_point_are_exempt() -> None:
    """Writing to the console is the job in both places, so neither is reported, and a module named
    `bindings` is read as a whole segment rather than as a `bin` directory.
    """
    printing = SyntaxNode(kind="call", name="print", text="print(total)", span=at(2))
    tested = DECLARED.model_copy(update={"path": "tests/test_orders.py"})
    entry = DECLARED.model_copy(update={"path": "src/cli.py"})
    bound = DECLARED.model_copy(update={"path": "src/bindings.py"})

    assert debug_artifact_left_behind(tested.of(printing, span=OPENING)) == 0
    assert debug_artifact_left_behind(entry.of(printing, span=OPENING)) == 0
    assert debug_artifact_left_behind(bound.of(printing, span=OPENING)) == 1


def test_only_a_construct_that_opens_a_body_counts_toward_the_ceiling() -> None:
    """Depth is counted over the constructs that cost a reader a level and no others.

    By the fourth level the line in front of a reader needs three others held above it, while two
    levels are what an ordinary loop over a filtered list already costs. A call inside a comparison
    inside an argument reads on one line and costs nothing, and `maximum_depth` and `body_kinds`
    are what a project states when its ceiling or its block constructs differ.
    """
    deep = nested("loop", "branch", "loop", "branch")
    shallow = nested("loop", "branch")
    flat = nested("operation", "call", "index", "member", "collection")

    assert deeply_nested_body(deep) is True
    assert deeply_nested_body(deep, maximum_depth=5) is False
    assert deeply_nested_body(shallow) is False
    assert deeply_nested_body(shallow, maximum_depth=1) is True
    assert deeply_nested_body(flat) is False
    assert deeply_nested_body(deep, body_kinds=("loop",)) is False


def test_a_construct_is_measured_against_the_one_holding_it() -> None:
    """Where a construct closes and how deep it is written is what turns it into a level.

    A reader sees one flat decision where a language models `} else if {` as a branch inside, since
    every arm closes where the first one closes. With nothing locating a construct there is no
    indentation to compare it against, so it is measured as written.
    """
    arms = chain(582, 577, 575)
    unplaced = DECLARED.of(
        SyntaxNode(
            kind="branch",
            text="if order.open:",
            children=[SyntaxNode(kind="loop", text="for item in order.items:")],
        ),
        span=OPENING,
    )

    assert deeply_nested_body(arms) is False
    assert deeply_nested_body(arms, maximum_depth=0) is True
    assert deeply_nested_body(unplaced) is False
    assert deeply_nested_body(unplaced, maximum_depth=1) is True


def test_a_declaration_with_no_tree_states_nothing_any_rule_can_read() -> None:
    """A family nobody asked for carries no tree, and every rule here reads code, so each one
    reports nothing rather than guessing at branches, statements, artifacts, or depth.
    """
    subject = DECLARED.around(None)

    assert superfluous_else_after_jump(subject) == 0
    assert statement_without_effect(subject) == 0
    assert debug_artifact_left_behind(subject) == 0
    assert deeply_nested_body(subject) is False
