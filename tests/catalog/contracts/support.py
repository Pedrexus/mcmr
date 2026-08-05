from types import ModuleType

from mcmr.domain.contracts import RuleContract


def module_with(name: str, **members: RuleContract) -> ModuleType:
    """Create one synthetic rule module for catalog tests."""
    module = ModuleType(name)
    module.__dict__.update(members)
    return module
