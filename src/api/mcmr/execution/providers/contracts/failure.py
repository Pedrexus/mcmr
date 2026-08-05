class ProviderExecutionError(RuntimeError):
    """Report one external provider failure without exposing an internal traceback."""

    def __init__(self, provider: str, problem: Exception) -> None:
        super().__init__(f"external provider `{provider}` failed validation, {problem}")
