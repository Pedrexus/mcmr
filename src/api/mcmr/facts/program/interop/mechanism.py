from enum import StrEnum, auto


class InteropMechanism(StrEnum):
    """Name how one language reaches another."""

    BINARY = auto()
    CONSOLE_SCRIPT = "console-script"
    NATIVE_MODULE = "native-module"
    SHARED_LIBRARY = "shared-library"
    KERNEL = auto()
