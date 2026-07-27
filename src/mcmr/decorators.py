from .models import Function, Rule, RuleOutcome


def rule[**P, Result: RuleOutcome](function: Function[P, Result]) -> Rule[P, Result]:
    """Wrap one typed rule function with source-linked fix declarations."""
    return Rule(
        function=function,
        module=function.__module__,
        qualname=function.__qualname__,
    )
