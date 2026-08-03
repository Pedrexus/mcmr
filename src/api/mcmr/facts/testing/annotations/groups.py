from patos import FrozenModel


class TypeAnnotationFields(FrozenModel):
    """Retain annotation path, union members, resolved names, and constraint recipe."""

    path: str
    union_members: list[str] = []
    resolved_names: list[str] = []
    constraint_recipe: str = ""
