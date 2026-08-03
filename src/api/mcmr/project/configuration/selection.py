from fnmatch import fnmatchcase


def is_match(*, rule_id: str, callable_path: str, pattern: str) -> bool:
    """Match one exact, prefix, shell-style, or callable selection pattern."""
    callable_pattern = pattern.replace("/", ".")
    if any(token in pattern for token in "*?["):
        return fnmatchcase(rule_id, pattern) or fnmatchcase(callable_path, callable_pattern)
    return rule_id == pattern or rule_id.startswith(pattern) or callable_pattern in callable_path
