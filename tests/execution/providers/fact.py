from mcmr.plugins import Fact


class PluginFact(Fact):
    """Carry one external plugin value for provider discovery tests."""

    external_evidence = True
    value: str
