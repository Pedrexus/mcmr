from .contextual.models.r1001 import model_foundation
from .contextual.models.r1002 import shared_model_placement
from .contextual.type_checking.r1001 import shared_typing_placement
from .deterministic.asyncio.compatibility import (
    deprecated_asyncio_coroutine_function_check,
    deprecated_event_loop_policy_usage,
)
from .deterministic.asyncio.orchestration import (
    asyncio_run_boundary,
    default_executor_to_thread_candidate,
    task_group_candidate,
)
from .deterministic.caching.r0001 import instance_independent_cached_property
from .deterministic.caching.r0002 import cached_instance_method
from .deterministic.classes.descriptors import (
    direct_method_descriptor_call_count,
    duplicate_component_attribute_alias_count,
    dynamic_super_receiver,
)
from .deterministic.classes.inheritance import (
    artificial_single_subclass_base_count,
    hazardous_multiple_inheritance_mro_count,
    pass_through_inheritance_layer_count,
)
from .deterministic.classes.organization import (
    coupled_nested_type_candidate,
    explicit_registry_name,
)
from .deterministic.classes.utilities import (
    staticmethod_calling_classmethod_count,
    utility_namespace_class_count,
)
from .deterministic.cli.r0001 import argparse_cli_construction
from .deterministic.collections.annotations import concrete_collection_parameter
from .deterministic.collections.construction import (
    explicit_tuple_construction,
    literal_pair_sequence_mapping_candidate,
    local_collection_representation_candidate,
)
from .deterministic.comprehensions.r0002 import comprehension_loop_count
from .deterministic.comprehensions.r0003 import manual_set_comprehension
from .deterministic.constants.r0001 import public_module_constant
from .deterministic.constants.r0002 import cross_module_project_constant_import
from .deterministic.constants.r0003 import dependency_safe_constant_order
from .deterministic.cuda_python import (
    blocking_raw_memory_operation_in_stream_scope,
    device_wide_synchronization_in_stream_scope,
    direct_cuda_core_lifecycle_construction,
    legacy_default_stream_launch,
)
from .deterministic.dead_code.r0001 import unreferenced_private_function
from .deterministic.documentation.r0001 import compact_house_docstring
from .deterministic.documentation.r0002 import tensor_docstring_semantics
from .deterministic.enumerations.organization import (
    shared_enum_file_shape,
    shared_enums_module_candidate,
)
from .deterministic.enumerations.values import (
    parallel_enum_metadata,
    prefer_enum_conversion,
    redundant_enum_value,
)
from .deterministic.exceptions.handling import nullable_exception_return_suppression
from .deterministic.exceptions.r0001 import broad_try_literal_setup
from .deterministic.exceptions.r0002 import bounded_exception_region
from .deterministic.exceptions.r0003 import shared_exception_placement
from .deterministic.functions.r0004 import unjustified_positional_only_parameter_count
from .deterministic.imports.hygiene import (
    bypassed_public_import,
    import_module_depth,
    unused_import,
)
from .deterministic.imports.style import (
    internal_relative_import,
    project_private_import,
    relative_import_beyond_package,
)
from .deterministic.interfaces.r0001 import concrete_isinstance_capability
from .deterministic.interfaces.r0002 import single_implementation_abstract_base
from .deterministic.logging.r0001 import logger_boundary_bypass_count
from .deterministic.models.construction import (
    manual_model_attribute_projection_count,
    standard_dataclass_model,
)
from .deterministic.models.organization import (
    approved_model_foundation,
    empty_declarative_model,
    shared_model_file_shape,
)
from .deterministic.modules import (
    empty_package_initializer,
    explicit_all_only_in_initializer,
    initializer_declaration,
    non_init_reexport_module,
    unused_explicit_export,
)
from .deterministic.naming.r0002 import boolean_predicate_name
from .deterministic.naming.r0003 import attribute_visibility
from .deterministic.numba_cuda import (
    conditional_block_barrier,
    default_stream_numba_kernel_launch,
    device_wide_numba_synchronization_in_stream_scope,
    dynamic_kernel_array_shape,
    kernel_return_value,
    synchronous_transfer_in_numba_stream_scope,
    unguarded_grid_index,
)
from .deterministic.performance.r0006 import tensor_interoperability_round_trip_count
from .deterministic.pydantic.construction import (
    constructor_model_candidate,
    optional_variant_discriminated_union_candidate,
    redundant_model_validate,
)
from .deterministic.pydantic.fields import (
    implicit_arbitrary_type_model,
    variadic_tuple_model_field,
)
from .deterministic.pydantic.validation import (
    declarative_field_constraint_candidate,
    imperative_model_input_validation,
    single_field_model_validator,
)
from .deterministic.sqlalchemy.results import (
    sqlmodel_execute_scalars_api,
    sqlmodel_primary_key_get,
    sqlmodel_redundant_scalars,
)
from .deterministic.sqlalchemy.sessions import (
    async_session_expiration_policy,
    session_commit_inside_loop,
)
from .deterministic.testing.async_checks import (
    synchronous_test_asyncio_run_count,
    unowned_async_test_count,
)
from .deterministic.testing.cases import (
    manual_literal_test_case_loop_count,
    parametrization_candidate_group_count,
)
from .deterministic.testing.coverage import (
    finite_range_hypothesis_candidate_count,
    owned_test_statement_count,
)
from .deterministic.testing.discovery import (
    conftest_import,
    legacy_tmpdir_fixture_count,
    pytest_import_isolation,
)
from .deterministic.testing.property_testing import (
    broad_example_property_candidate_count,
    module_generated_parametrization_count,
)
from .deterministic.testing.redundancy import (
    concentrated_test_reach_cluster_count,
    duplicate_test_intent_cluster_count,
    production_reach_hotspot_count,
)
from .deterministic.testing.state import (
    conditional_test_branch_count,
    direct_shared_test_state_mutation_count,
)
from .deterministic.testing.suite import (
    async_runner_auto_mode_conflict,
    coverage_without_branch_measurement,
    pytest_configuration_strictness,
)
from .deterministic.torch.r0001 import fluent_tensor_call_chain
from .deterministic.type_checking.annotations import (
    prohibited_annotation,
    repeated_annotated_constraint,
)
from .deterministic.type_checking.casts import redundant_boolean_conversion, repeated_cast_patterns
from .deterministic.type_checking.declarations import (
    future_annotations_import,
    minimum_python_declaration,
    nullable_boolean_annotation,
)

__all__ = [
    "approved_model_foundation",
    "argparse_cli_construction",
    "artificial_single_subclass_base_count",
    "async_runner_auto_mode_conflict",
    "async_session_expiration_policy",
    "asyncio_run_boundary",
    "attribute_visibility",
    "boolean_predicate_name",
    "blocking_raw_memory_operation_in_stream_scope",
    "bounded_exception_region",
    "broad_example_property_candidate_count",
    "broad_try_literal_setup",
    "bypassed_public_import",
    "cached_instance_method",
    "compact_house_docstring",
    "comprehension_loop_count",
    "concrete_collection_parameter",
    "concrete_isinstance_capability",
    "conditional_block_barrier",
    "conditional_test_branch_count",
    "concentrated_test_reach_cluster_count",
    "conftest_import",
    "constructor_model_candidate",
    "coupled_nested_type_candidate",
    "coverage_without_branch_measurement",
    "cross_module_project_constant_import",
    "declarative_field_constraint_candidate",
    "default_stream_numba_kernel_launch",
    "default_executor_to_thread_candidate",
    "dependency_safe_constant_order",
    "deprecated_asyncio_coroutine_function_check",
    "deprecated_event_loop_policy_usage",
    "device_wide_synchronization_in_stream_scope",
    "device_wide_numba_synchronization_in_stream_scope",
    "direct_cuda_core_lifecycle_construction",
    "direct_method_descriptor_call_count",
    "direct_shared_test_state_mutation_count",
    "duplicate_test_intent_cluster_count",
    "duplicate_component_attribute_alias_count",
    "dynamic_kernel_array_shape",
    "dynamic_super_receiver",
    "empty_declarative_model",
    "empty_package_initializer",
    "explicit_all_only_in_initializer",
    "explicit_registry_name",
    "explicit_tuple_construction",
    "finite_range_hypothesis_candidate_count",
    "fluent_tensor_call_chain",
    "future_annotations_import",
    "hazardous_multiple_inheritance_mro_count",
    "imperative_model_input_validation",
    "implicit_arbitrary_type_model",
    "import_module_depth",
    "initializer_declaration",
    "instance_independent_cached_property",
    "internal_relative_import",
    "kernel_return_value",
    "legacy_default_stream_launch",
    "legacy_tmpdir_fixture_count",
    "literal_pair_sequence_mapping_candidate",
    "local_collection_representation_candidate",
    "logger_boundary_bypass_count",
    "manual_literal_test_case_loop_count",
    "manual_model_attribute_projection_count",
    "manual_set_comprehension",
    "minimum_python_declaration",
    "model_foundation",
    "module_generated_parametrization_count",
    "non_init_reexport_module",
    "nullable_boolean_annotation",
    "nullable_exception_return_suppression",
    "optional_variant_discriminated_union_candidate",
    "owned_test_statement_count",
    "parallel_enum_metadata",
    "parametrization_candidate_group_count",
    "pass_through_inheritance_layer_count",
    "prefer_enum_conversion",
    "prohibited_annotation",
    "project_private_import",
    "public_module_constant",
    "production_reach_hotspot_count",
    "pytest_configuration_strictness",
    "pytest_import_isolation",
    "redundant_boolean_conversion",
    "redundant_enum_value",
    "redundant_model_validate",
    "relative_import_beyond_package",
    "repeated_annotated_constraint",
    "repeated_cast_patterns",
    "session_commit_inside_loop",
    "shared_enum_file_shape",
    "shared_enums_module_candidate",
    "shared_exception_placement",
    "shared_model_file_shape",
    "shared_model_placement",
    "shared_typing_placement",
    "single_field_model_validator",
    "single_implementation_abstract_base",
    "sqlmodel_execute_scalars_api",
    "sqlmodel_primary_key_get",
    "sqlmodel_redundant_scalars",
    "standard_dataclass_model",
    "staticmethod_calling_classmethod_count",
    "synchronous_transfer_in_numba_stream_scope",
    "synchronous_test_asyncio_run_count",
    "task_group_candidate",
    "tensor_docstring_semantics",
    "tensor_interoperability_round_trip_count",
    "unjustified_positional_only_parameter_count",
    "unguarded_grid_index",
    "unowned_async_test_count",
    "unreferenced_private_function",
    "unused_explicit_export",
    "unused_import",
    "utility_namespace_class_count",
    "variadic_tuple_model_field",
]
