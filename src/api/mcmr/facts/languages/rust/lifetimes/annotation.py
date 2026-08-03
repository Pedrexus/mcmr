from .groups import LifetimeAnnotationFields


class LifetimeAnnotation(LifetimeAnnotationFields):
    """Retain one declaration and every position where it names a lifetime."""

    beyond: list[str] = []
    required_by_syntax: list[str] = []
