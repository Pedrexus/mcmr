from typing import Literal

from patos import FrozenModel

from pydantic import NonNegativeInt

from ...foundation import SourceSpan


class PydanticAnalysisFields:
    """Group flat Pydantic analysis fields by identity and construction."""

    class Field(FrozenModel):
        """Retain one model field annotation and its collection shape."""

        name: str
        annotation: str
        span: SourceSpan
        contains_variadic_tuple: bool = False

    class Validator(FrozenModel):
        """Retain structural evidence for one imported Pydantic validator."""

        kind: Literal["field", "model_after", "other"]
        fields_read: list[str] = []
        has_self_call: bool = False
        has_nonfield_access: bool = False
        declarative_constraint_count: NonNegativeInt = 0
        proves_disjoint_optional_variants: bool = False
        variant_count: NonNegativeInt = 0

    class Identity(FrozenModel):
        """Retain fields, validators, model role, foundation, and class form."""

        name: str
        fields: list[PydanticAnalysisFields.Field] = []
        validators: list[PydanticAnalysisFields.Validator] = []
        is_pydantic_model: bool = False
        uses_flexible_model: bool = False
        flexible_base_span: SourceSpan | None = None
        is_undecorated_plain_class: bool = False

    class Construction(Identity):
        """Retain constructor, storage, validation, and identity measurements."""

        synchronous_init_count: NonNegativeInt = 0
        fixed_parameter_count: NonNegativeInt = 0
        stored_parameter_count: NonNegativeInt = 0
        validation_count: NonNegativeInt = 0
        default_count: NonNegativeInt = 0
        has_only_data_identity_methods: bool = False


PydanticFieldAnalysis = PydanticAnalysisFields.Field
PydanticValidator = PydanticAnalysisFields.Validator
