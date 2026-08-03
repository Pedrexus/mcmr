from pydantic import TypeAdapter

from ....domain.contracts import RuleSetting


def validated_setting(annotation: type, value: RuleSetting) -> RuleSetting:
    """Validate one setting against its rule annotation and retain supported value shapes."""
    answer = TypeAdapter[RuleSetting](annotation).validate_python(value)
    if isinstance(answer, bool | int | float | str):
        return answer
    if isinstance(answer, tuple | list) and all(isinstance(item, str) for item in answer):
        return list(answer)
    if isinstance(answer, set) and all(isinstance(item, str) for item in answer):
        return set(answer)
    raise TypeError(f"Rule setting has unsupported type {type(answer).__name__}")
