from ..... import rule
from .....facts import StringExpressionFact
from .....models import Count, Replace, SourceRewrite


@rule
def fragmented_multiline_literal(
    subject: StringExpressionFact, *, minimum_fragments: int = 2
) -> Count:
    """Count multiline values assembled from adjacent literal fragments.

    Definition
    ----------
    Inspect folded string constants whose runtime value contains at least one newline. Count the
    lexical string tokens that Python implicitly concatenates and report the expression when the
    count reaches `minimum_fragments`. A triple-quoted literal is one token and is not reported.
    Adjacent fragments used only to wrap one runtime line are also excluded.

    Evidence
    --------
    Every finding gives the complete expression range and its literal-fragment count. The result
    value is the number of reported expressions.

    Exceptions
    ----------
    Keep fragments when exact indentation, escaping, translation extraction, generated text, or
    a deliberate trailing-newline policy is clearer than a triple-quoted value. Triple-quoted
    strings can change whitespace and therefore receive no automatic fix. Ruff ISC003 separately
    prefers implicit adjacency over an explicit `+` between literals.

    Examples
    --------
    `("first line\\n" "second line\\n")` is reported as a two-fragment multiline value. One
    triple-quoted value containing both lines is accepted. `("one long " "runtime line")` is
    accepted because changing it to a multiline literal would change its value.

    References
    ----------
    Cites "The Python Language Reference", string literal concatenation
    https://docs.python.org/3/reference/lexical_analysis.html#string-literal-concatenation
    Generalizes Ruff ISC003 explicit-string-concatenation
    https://docs.astral.sh/ruff/rules/explicit-string-concatenation/
    """
    return sum(
        "\n" in expression.runtime_value
        and expression.literal_fragment_count >= minimum_fragments
        and not expression.wraps_single_runtime_line
        for expression in subject.expressions
    )


@fragmented_multiline_literal.fix(is_default=True)
def use_multiline_literal(
    subject: StringExpressionFact, *, minimum_fragments: int = 2
) -> list[SourceRewrite]:
    """State each fragmented value once as a single multiline literal.

    Only a language whose multiline delimiter this rule knows can be rewritten here, so the plan
    stays empty until a language backend can render the literal itself.
    """
    if subject.language != "python":
        return []
    return [
        Replace(target=expression.node, source=f'"""{expression.runtime_value}"""')
        for expression in subject.expressions
        if expression.node is not None
        and "\n" in expression.runtime_value
        and expression.literal_fragment_count >= minimum_fragments
        and '"' not in expression.runtime_value
    ]
