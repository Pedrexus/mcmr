use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionInputValidation {
    pub is_model_method: bool,
    pub is_pydantic_validator: bool,
    pub checks_raw_input_type: bool,
    pub raises_validation_exception: bool,
}
