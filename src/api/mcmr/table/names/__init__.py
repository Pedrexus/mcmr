from .calls import CallRelation
from .classes import ClassRelation
from .common import GenericRelation, ImportBindingRelation, SyntaxRelation
from .functions import FunctionRelation

__all__ = [
    "CallRelation",
    "ClassRelation",
    "FunctionRelation",
    "GenericRelation",
    "ImportBindingRelation",
    "SyntaxRelation",
]
