use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionOutputValidation {
    pub is_raise_body: bool,
    pub returns_single_call: bool,
    pub forwards_only_parameter_unchanged: bool,
    pub constructs_owner_model: bool,
}
