from enum import StrEnum, auto


class _GraphKinds:
    """Own the closed vocabulary used by repository graphs."""

    class Language(StrEnum):
        """Name the language that declared one symbol."""

        PYTHON = auto()
        RUST = auto()
        TYPESCRIPT = auto()
        C = auto()
        CPP = auto()
        CUDA = auto()

        @property
        def separator(self) -> str:
            """Return what this language writes between a holder and its name."""
            dotted = {_GraphKinds.Language.PYTHON, _GraphKinds.Language.TYPESCRIPT}
            return "." if self in dotted else "::"

    class Node(StrEnum):
        """Name what one node of the repository graph is."""

        REPOSITORY = auto()
        DIRECTORY = auto()
        FILE = auto()
        MODULE = auto()
        CLASS = auto()
        FUNCTION = auto()
        METHOD = auto()
        PROPERTY = auto()
        ATTRIBUTE = auto()
        VARIABLE = auto()
        PARAMETER = auto()
        EXTERNAL_MODULE = "external-module"
        EXTERNAL_SYMBOL = "external-symbol"
        UNRESOLVED_SYMBOL = "unresolved-symbol"

    class Edge(StrEnum):
        """Name what one relationship between two graph nodes is."""

        CONTAIN = auto()
        DEFINE = auto()
        IMPORT = auto()
        CALL = auto()
        INSTANTIATE = auto()
        INHERIT = auto()
        TYPED = auto()
        ACCESS = auto()

    class Resolution(StrEnum):
        """Say how completely one relationship was resolved."""

        EXACT = auto()
        EXTERNAL = auto()
        UNRESOLVED = auto()


EdgeKind = _GraphKinds.Edge
Language = _GraphKinds.Language
NodeKind = _GraphKinds.Node
Resolution = _GraphKinds.Resolution
