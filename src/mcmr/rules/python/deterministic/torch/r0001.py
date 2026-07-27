from ..... import rule
from .....facts import CallFact, CallSite, Expression, LiteralKind
from .....models import Count, Replace, SourceRewrite

_TENSOR_METHODS = {
    "torch.abs": "abs",
    "torch.acos": "acos",
    "torch.asin": "asin",
    "torch.atan": "atan",
    "torch.ceil": "ceil",
    "torch.cos": "cos",
    "torch.cosh": "cosh",
    "torch.erf": "erf",
    "torch.erfinv": "erfinv",
    "torch.exp": "exp",
    "torch.exp2": "exp2",
    "torch.expm1": "expm1",
    "torch.floor": "floor",
    "torch.frac": "frac",
    "torch.log": "log",
    "torch.log10": "log10",
    "torch.log1p": "log1p",
    "torch.log2": "log2",
    "torch.neg": "neg",
    "torch.reciprocal": "reciprocal",
    "torch.relu": "relu",
    "torch.round": "round",
    "torch.rsqrt": "rsqrt",
    "torch.sigmoid": "sigmoid",
    "torch.sign": "sign",
    "torch.sin": "sin",
    "torch.sinh": "sinh",
    "torch.sqrt": "sqrt",
    "torch.square": "square",
    "torch.tan": "tan",
    "torch.tanh": "tanh",
    "torch.trunc": "trunc",
}
_BASE_POWERS = {"2": "exp2", "2.0": "exp2"}
_POWER_FUNCTIONS = frozenset({"torch.pow", "torch.float_power"})


def folded_method(expression: Expression) -> tuple[str, Expression] | None:
    """Return the tensor method and receiver one module-level tensor call folds into."""
    method = _TENSOR_METHODS.get(expression.qualified_name, "")
    if method and len(expression.arguments) == 1:
        return method, expression.arguments[0]
    if expression.qualified_name in _POWER_FUNCTIONS and len(expression.arguments) == 2:
        base, operand = expression.arguments
        if base.literal_kind is LiteralKind.NUMBER and (power := _BASE_POWERS.get(base.text, "")):
            return power, operand
    return None


def fluent_chain(call: CallSite) -> tuple[Expression, list[str]] | None:
    """Return the tensor and the ordered methods one nested call chain folds into."""
    if call.is_shadowed or call.keyword_names:
        return None
    methods: list[str] = []
    current = Expression(
        text=call.node.text if call.node is not None else "",
        qualified_name=call.qualified_name,
        arguments=call.arguments,
    )
    while (folded := folded_method(current)) is not None:
        method, receiver = folded
        methods.append(method)
        current = receiver
    if not methods:
        return None
    methods.reverse()
    return current, methods


def chain_source(call: CallSite, tensor: Expression, methods: list[str]) -> str:
    """Render the fluent chain, in place when the value is rebound to its own tensor."""
    suffix = "_" if call.assigned_target and call.assigned_target == tensor.text else ""
    return tensor.text + "".join(f".{method}{suffix}()" for method in methods)


@rule
def fluent_tensor_call_chain(subject: CallFact, *, minimum_operations: int = 2) -> Count:
    """Count nested Torch function calls that a fluent tensor chain states more directly.

    Definition
    ----------
    Resolve unshadowed Torch functions whose behavior a tensor already exposes as a method, then
    fold each nested application over one tensor into the chain it is equivalent to. Report a call
    whose chain reaches `minimum_operations` operations, because that is the point where the nested
    form reverses reading order and hides the tensor the operations act on. A power over a literal
    base folds into the base method that names it, so `torch.pow(2.0, value)` joins the chain as
    `exp2`. The value is the number of nested calls found.

    Reading order is the whole argument. A fluent chain names the tensor once and then reads left
    to right in the order the operations run, while the nested form names the tensor last and reads
    inside out.

    Evidence
    --------
    Each finding records the outer call range, the resolved tensor, and the ordered methods the
    chain folds into. The rewrite chooses the in-place method of each operation only when the whole
    expression is rebound to the tensor it reads, since that assignment already discards the prior
    value and no other alias can observe the difference.

    Exceptions
    ----------
    A shadowed Torch alias, a keyword argument, an operation with no method form, and a chain
    shorter than `minimum_operations` are all left alone. A single call such as `torch.log2(value)`
    stays valid because there is no reading order to reverse. The rule does not claim that in-place
    operations are generally faster, only that a rebound value cannot observe them.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       sigma = torch.pow(2.0, torch.round(torch.log2(sigma)))
       scaled = torch.sqrt(torch.abs(weights))

    Good
    ~~~~
    .. code-block:: python

       sigma = sigma.log2_().round_().exp2_()
       scaled = weights.abs().sqrt()

    References
    ----------
    Cites "PyTorch documentation", Tensor method reference, including the in-place variants
    https://docs.pytorch.org/docs/stable/tensors.html
    Cites "PyTorch documentation", autograd notes on in-place operations
    https://docs.pytorch.org/docs/stable/notes/autograd.html#in-place-operations-with-autograd
    Cites "PyTorch documentation", `torch.pow`
    https://docs.pytorch.org/docs/stable/generated/torch.pow.html
    """
    return sum(
        (chain := fluent_chain(call)) is not None and len(chain[1]) >= minimum_operations
        for call in subject.calls
    )


@fluent_tensor_call_chain.fix(is_default=True)
def use_fluent_tensor_chain(
    subject: CallFact, *, minimum_operations: int = 2
) -> list[SourceRewrite]:
    """State each nested chain as the fluent tensor chain it is equivalent to."""
    resolved = [
        (call, chain)
        for call in subject.calls
        if call.node is not None and (chain := fluent_chain(call)) is not None
    ]
    return [
        Replace(target=call.node, source=chain_source(call, tensor, methods))
        for call, (tensor, methods) in resolved
        if call.node is not None and len(methods) >= minimum_operations
    ]
