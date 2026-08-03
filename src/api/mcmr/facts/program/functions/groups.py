from typing import TYPE_CHECKING, Literal

from ...foundation import Fact, NodeRef, Visibility

if TYPE_CHECKING:
    from pydantic import NonNegativeInt

    from .types import FunctionTypes


class FunctionFields:
    """Group contiguous function fields without changing their wire order."""

    class Execution(Fact):
        """Retain task, receiver, cache, and documentation evidence."""

        created_task_count: NonNegativeInt = 0
        is_test: bool = False
        gather_consumes_created_tasks: bool = False
        gather_returns_exceptions: bool = False
        has_task_group: bool = False
        reads_receiver: bool = False
        cache_decorator: Literal["", "cached_property", "cache", "lru_cache"] = ""

    class Identity(Execution):
        """Retain documentation, tensor semantics, and callable identity."""

        docstring: str = ""
        recognized_tensor_roles: list[str] = []
        has_tensor_shape_semantics: bool = False
        has_tensor_dtype_semantics: bool = False
        name: str = ""
        scope: Literal["module", "method", "nested"] = "module"
        visibility: Visibility = Visibility.PUBLIC

    class Address(Identity):
        """Retain protocol identity and exact source nodes."""

        is_protocol_name: bool = False
        definition: NodeRef | None = None
        body_expression: NodeRef | None = None
        references: list[NodeRef] = []

    class Source(Address):
        """Retain sole ownership evidence and direct source measures."""

        sole_reference_owner_definition: NodeRef | None = None
        implementation_lines: NonNegativeInt = 0
        direct_statement_count: NonNegativeInt = 0
        reference_count: NonNegativeInt = 0

    class Structure(Source):
        """Retain behavior, controls, parameters, decorators, and recursion."""

        behavior_operation_count: NonNegativeInt = 0
        conditional_count: NonNegativeInt = 0
        control_increments: list[FunctionTypes.ControlIncrement] = []
        parameters: list[FunctionTypes.Parameter] = []
        decorators: list[str] = []
        sole_reference_owner_class: str = ""
        is_async: bool = False

    class Contract(Structure):
        """Retain recursion, reference, and callable contract evidence."""

        is_recursive: bool = False
        is_first_class_reference: bool = False
        is_abstract: bool = False
        is_protocol_member: bool = False
        is_overload: bool = False
        is_property: bool = False
        is_framework_hook: bool = False

    class Body(Contract):
        """Retain framework, polymorphism, and compact-body evidence."""

        is_declarative_body: bool = False
        is_polymorphic: bool = False
        is_pass_body: bool = False
        is_raise_body: bool = False
        returns_single_call: bool = False
        forwards_only_parameter_unchanged: bool = False
        is_model_method: bool = False

    class Validation(Body):
        """Retain Pydantic and validation behavior."""

        is_pydantic_validator: bool = False
        checks_raw_input_type: bool = False
        raises_validation_exception: bool = False
        constructs_owner_model: bool = False
