use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct ParameterContract {
    pub is_positional_only: bool,
    pub is_keyword_only: bool,
    pub is_receiver: bool,
    pub is_required_by_external_contract: bool,
    pub has_boolean_annotation: bool,
    pub has_boolean_default: bool,
}
