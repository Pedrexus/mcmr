from ....domain.contracts import ModelProvenance
from .groups import ContextualTrialFields


class ContextualTrial(ContextualTrialFields.Outcome):
    """Retain one profile answer against one reviewed case."""


ContextualTrial.model_rebuild(_types_namespace={"ModelProvenance": ModelProvenance})
