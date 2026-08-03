from .groups import SymbolReachFields


class SymbolReach(SymbolReachFields.Operations):
    """Retain one declaration and the spread of every reference reaching it."""
