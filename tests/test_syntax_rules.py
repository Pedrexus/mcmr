from mcmr.facts import FunctionFact, FunctionParameter, SyntaxNode
from mcmr.rules.general.deterministic.naming.r0001 import uninformative_local_name
from mcmr.rules.general.deterministic.parameters.r0003 import positional_boolean_parameter
from tests.conftest import Declaration

DECLARED = Declaration(path="src/loader.py", qualname="load", source="def load(path):\n    ...\n")
SPAN = DECLARED.span


def binding(name: str) -> SyntaxNode:
    """Build one node standing for a local binding."""
    return SyntaxNode(kind="binding", name=name, text=f"{name} = read()")


def signature(*parameters: FunctionParameter, language: str = "python") -> FunctionFact:
    """Build one function fact stating the parameters a caller meets."""
    return FunctionFact(
        key="function:src/render.py:render",
        span=SPAN,
        language=language,
        name="render",
        parameters=list(parameters),
    )


def test_a_name_too_short_to_say_what_it_holds_is_reported() -> None:
    """A brief local name is reported and a conventional index is left alone.

    A local name is the cheapest documentation a body has and the only one that cannot stale, while
    `i` in a loop is a convention older than the code and reads fine.
    """
    subject = DECLARED.of(binding("d"), binding("raw"), binding("r"))

    assert uninformative_local_name(subject).value == 2
    assert uninformative_local_name(subject, minimum_length=1).value == 0
    assert uninformative_local_name(DECLARED.of(binding("i"), binding("n"))).value == 0


def test_only_a_callable_carrying_a_tree_is_judged() -> None:
    """The rule reads the locals a callable binds and declines everything else.

    A fact carrying no tree was never asked to carry one, and `id` on a model reads fine where the
    same `id` inside a function body does not.
    """
    field = DECLARED.model_copy(update={"kind": "type"}).of(binding("id"))

    assert uninformative_local_name(DECLARED.around(None)).value == 0
    assert uninformative_local_name(field).value == 0
    assert uninformative_local_name(DECLARED.of(binding("id"))).value == 1


def test_the_tree_navigates_the_way_a_rule_reads_it() -> None:
    """Walking, narrowing by kind, and measuring depth are what make a style rule writable."""
    tree = SyntaxNode(
        kind="callable",
        name="load",
        children=[
            SyntaxNode(kind="binding", name="raw", children=[SyntaxNode(kind="call", name="read")])
        ],
    )

    assert [node.kind for node in tree.walk()] == ["callable", "binding", "call"]
    assert tree.names("call") == ["read"]
    assert [node.name for node in tree.of_kind("binding", "call")] == ["raw", "read"]
    assert tree.depth == 3


def test_a_positional_boolean_reads_as_nothing_at_the_call_site() -> None:
    """`render(document, True, False)` says nothing about what is true, in any language."""
    trapped = signature(
        FunctionParameter(name="document"),
        FunctionParameter(name="inline", type_name="bool"),
        FunctionParameter(name="minified", has_boolean_annotation=True),
    )
    named = signature(
        FunctionParameter(name="document"),
        FunctionParameter(name="inline", type_name="bool", is_keyword_only=True),
    )
    rust = signature(
        FunctionParameter(name="self", type_name="bool", is_receiver=True),
        FunctionParameter(name="inline", type_name="bool"),
        language="rust",
    )

    assert positional_boolean_parameter(trapped) == 2
    assert positional_boolean_parameter(named) == 0
    assert positional_boolean_parameter(rust) == 1
