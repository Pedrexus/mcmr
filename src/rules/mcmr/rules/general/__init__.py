from .contextual.architecture.boundaries import (
    dependency_boundary_alignment,
    dependency_hub_quality,
)
from .contextual.architecture.cohesion import ModuleCohesion, module_cohesion
from .contextual.architecture.evolution import component_balance
from .contextual.architecture.responsibilities import mixed_class_responsibilities
from .contextual.classes.r1001 import inheritance_design
from .contextual.classes.r1002 import substitutability
from .contextual.comments.r1001 import comment_intent
from .contextual.comments.r1002 import comment_accuracy
from .contextual.deployment.exposure import exposure_control
from .contextual.deployment.rollout import (
    progressive_rollout,
    rollback_readiness,
    rollout_success_criteria,
)
from .contextual.design.r1001 import primitive_obsession
from .contextual.duplication.r1001 import semantic_duplication
from .contextual.functions.r1001 import AbstractionLevel, abstraction_level
from .contextual.performance.complexity import algorithmic_complexity
from .contextual.reliability.r1003 import bounded_work
from .contextual.strings.r1001 import string_construction_mechanism
from .contextual.writing import comment_language, docstring_language
from .deterministic.architecture.dependencies import (
    abstraction_nothing_depends_on,
    dependency_on_a_less_stable_module,
    import_cycles,
)
from .deterministic.architecture.fitness import architecture_fitness_coverage
from .deterministic.bindings.r0001 import unreached_cross_language_artifact
from .deterministic.bindings.r0002 import cross_language_boundary_width
from .deterministic.branches.r0001 import value_dispatch_candidate
from .deterministic.calls.r0001 import unchecked_result_call
from .deterministic.calls.r0002 import unbounded_blocking_call
from .deterministic.ci.r0001 import continuous_integration
from .deterministic.ci.r0002 import feedback_target_coverage
from .deterministic.classes.organization import class_method_order
from .deterministic.classes.shape import ancestor_count, declared_field_count, public_method_count
from .deterministic.comments.content import (
    comment_length,
    commented_out_code,
    unresolved_work_marker,
)
from .deterministic.configuration.r0001 import hardcoded_path_policy_count
from .deterministic.control.artifacts import debug_artifact_left_behind
from .deterministic.control.flow import (
    deeply_nested_body,
    statement_without_effect,
    superfluous_else_after_jump,
)
from .deterministic.coupling import PackageCoupling
from .deterministic.data_assets.governance import (
    data_asset_governance_gap,
    unhealthy_data_dependency,
)
from .deterministic.data_assets.lineage import (
    data_change_test_gap_percentage,
    unresolved_lineage_endpoint,
)
from .deterministic.data_assets.references import (
    missing_data_asset_reference,
    missing_data_field_reference,
    nonactive_data_asset_reference,
)
from .deterministic.data_assets.schema import (
    data_definition_gap_percentage,
    incompatible_data_field_type,
)
from .deterministic.dependencies.state import (
    dependency_evidence_gap_percentage,
    dependency_technical_lag,
    explicit_dependency_state_count,
)
from .deterministic.dependencies.transformations import (
    repeated_external_unary_transformation,
)
from .deterministic.deployment.r0001 import deployment_reproducibility
from .deterministic.duplication.source import (
    duplicated_repository_share,
    pasted_block_copy_count,
    repeated_class_method_count,
)
from .deterministic.duplication.values import repeated_semantic_string_literal
from .deterministic.encapsulation.r0001 import external_nonpublic_attribute_access_count
from .deterministic.errors.handling import (
    raise_inside_guarded_region,
    raise_without_cause,
    swallowed_error,
)
from .deterministic.errors.taxonomy import vanilla_error_type
from .deterministic.filesystem import (
    directory_module_count,
    directory_pathway,
    empty_directories,
    package_depth,
)
from .deterministic.functions.boundaries import (
    reflective_scope_read,
    required_parameter_count,
    transparent_unary_wrapper,
)
from .deterministic.functions.flow import (
    cognitive_complexity,
    function_conditional_count,
    nesting_depth,
)
from .deterministic.functions.ownership import (
    class_owned_module_helper,
    single_use_trivial_helper,
    unnecessary_one_line_concrete_function,
)
from .deterministic.functions.size import (
    function_statement_count,
    shallow_callable,
)
from .deterministic.history.hotspots import (
    coupled_files_that_never_name_each_other,
    file_too_many_hands_have_touched,
    large_file_the_team_keeps_reopening,
)
from .deterministic.lifecycle.r0001 import project_automation
from .deterministic.lifecycle.r0002 import feature_flag_debt
from .deterministic.modules.shape import (
    module_class_count,
    module_inception,
    non_ascii_source_path,
)
from .deterministic.modules.size import (
    module_line_count,
    module_member_count,
    module_statement_count,
)
from .deterministic.naming.r0001 import uninformative_local_name
from .deterministic.observability.r0003 import alert_actionability
from .deterministic.observability.r0004 import service_objective_coverage
from .deterministic.onboarding.r0001 import onboarding_readiness
from .deterministic.operations.r0001 import runbook_coverage
from .deterministic.overrides.finality import (
    final_class_subclassed,
    final_method_overridden,
    inherited_attribute_hides_a_method,
)
from .deterministic.overrides.initialization import (
    initializer_called_on_a_stranger,
    subclass_initializer_skips_its_base,
)
from .deterministic.overrides.parameters import (
    overriding_method_accepts_different_arguments,
    overriding_method_demands_an_argument_the_base_defaulted,
    overriding_method_renames_a_parameter,
)
from .deterministic.overrides.protocols import (
    abstract_member_left_unimplemented,
    overriding_method_changes_its_call_protocol,
)
from .deterministic.parameters.booleans import (
    boolean_parameter_count,
    positional_boolean_parameter,
)
from .deterministic.parameters.design import (
    configuration_object_parameter,
    swappable_parameter_pair,
)
from .deterministic.performance.r0003 import regression_guard_coverage
from .deterministic.reach.scope import (
    file_local_public_declaration,
    repository_wide_declaration,
    unreferenced_public_declaration,
)
from .deterministic.reviews.r0002 import review_coverage
from .deterministic.routes.declarations import (
    duplicate_route_declaration,
    inconsistent_route_path_style,
    unreached_declared_route,
)
from .deterministic.security.secrets import unseeded_randomness_for_secrets, weak_hashing_primitive
from .deterministic.security.shells import (
    command_built_from_a_shell_string,
    credential_written_into_source,
)
from .deterministic.strings.r0001 import fragmented_multiline_literal
from .deterministic.strings.r0003 import decorative_repeated_separator_count
from .deterministic.testing.r0008 import flaky_test_quarantine_debt
from .deterministic.waivers.r0001 import waiver_debt
from .deterministic.writing.patterns import (
    ai_associated_pattern_count,
    sentence_opener_concentration,
)
from .deterministic.writing.rhythm import paragraph_length_uniformity, sentence_length_uniformity

__all__ = [
    "AbstractionLevel",
    "ModuleCohesion",
    "PackageCoupling",
    "abstract_member_left_unimplemented",
    "abstraction_level",
    "abstraction_nothing_depends_on",
    "ai_associated_pattern_count",
    "alert_actionability",
    "algorithmic_complexity",
    "ancestor_count",
    "architecture_fitness_coverage",
    "boolean_parameter_count",
    "bounded_work",
    "class_method_order",
    "class_owned_module_helper",
    "cognitive_complexity",
    "command_built_from_a_shell_string",
    "comment_accuracy",
    "comment_intent",
    "comment_language",
    "comment_length",
    "commented_out_code",
    "component_balance",
    "configuration_object_parameter",
    "continuous_integration",
    "coupled_files_that_never_name_each_other",
    "credential_written_into_source",
    "cross_language_boundary_width",
    "data_asset_governance_gap",
    "data_change_test_gap_percentage",
    "data_definition_gap_percentage",
    "debug_artifact_left_behind",
    "declared_field_count",
    "decorative_repeated_separator_count",
    "deeply_nested_body",
    "dependency_boundary_alignment",
    "dependency_evidence_gap_percentage",
    "dependency_hub_quality",
    "dependency_on_a_less_stable_module",
    "dependency_technical_lag",
    "deployment_reproducibility",
    "directory_module_count",
    "directory_pathway",
    "docstring_language",
    "duplicate_route_declaration",
    "duplicated_repository_share",
    "empty_directories",
    "explicit_dependency_state_count",
    "exposure_control",
    "external_nonpublic_attribute_access_count",
    "feature_flag_debt",
    "feedback_target_coverage",
    "file_local_public_declaration",
    "file_too_many_hands_have_touched",
    "final_class_subclassed",
    "final_method_overridden",
    "flaky_test_quarantine_debt",
    "fragmented_multiline_literal",
    "function_conditional_count",
    "function_statement_count",
    "hardcoded_path_policy_count",
    "import_cycles",
    "incompatible_data_field_type",
    "inconsistent_route_path_style",
    "inheritance_design",
    "inherited_attribute_hides_a_method",
    "initializer_called_on_a_stranger",
    "large_file_the_team_keeps_reopening",
    "missing_data_asset_reference",
    "missing_data_field_reference",
    "mixed_class_responsibilities",
    "module_class_count",
    "module_cohesion",
    "module_inception",
    "module_line_count",
    "module_member_count",
    "module_statement_count",
    "nesting_depth",
    "non_ascii_source_path",
    "nonactive_data_asset_reference",
    "onboarding_readiness",
    "overriding_method_accepts_different_arguments",
    "overriding_method_changes_its_call_protocol",
    "overriding_method_demands_an_argument_the_base_defaulted",
    "overriding_method_renames_a_parameter",
    "package_depth",
    "paragraph_length_uniformity",
    "pasted_block_copy_count",
    "positional_boolean_parameter",
    "primitive_obsession",
    "progressive_rollout",
    "project_automation",
    "public_method_count",
    "raise_inside_guarded_region",
    "raise_without_cause",
    "reflective_scope_read",
    "regression_guard_coverage",
    "repeated_class_method_count",
    "repeated_external_unary_transformation",
    "repeated_semantic_string_literal",
    "repository_wide_declaration",
    "required_parameter_count",
    "review_coverage",
    "rollback_readiness",
    "rollout_success_criteria",
    "runbook_coverage",
    "semantic_duplication",
    "sentence_length_uniformity",
    "sentence_opener_concentration",
    "service_objective_coverage",
    "shallow_callable",
    "single_use_trivial_helper",
    "statement_without_effect",
    "string_construction_mechanism",
    "subclass_initializer_skips_its_base",
    "substitutability",
    "superfluous_else_after_jump",
    "swallowed_error",
    "swappable_parameter_pair",
    "transparent_unary_wrapper",
    "unbounded_blocking_call",
    "unchecked_result_call",
    "unhealthy_data_dependency",
    "uninformative_local_name",
    "unnecessary_one_line_concrete_function",
    "unreached_cross_language_artifact",
    "unreached_declared_route",
    "unreferenced_public_declaration",
    "unresolved_lineage_endpoint",
    "unresolved_work_marker",
    "unseeded_randomness_for_secrets",
    "value_dispatch_candidate",
    "vanilla_error_type",
    "waiver_debt",
    "weak_hashing_primitive",
]
