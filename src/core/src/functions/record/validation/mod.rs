use serde::Serialize;

mod input;
mod output;

pub use input::FunctionInputValidation;
pub use output::FunctionOutputValidation;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionValidation {
    #[serde(flatten)]
    pub input: FunctionInputValidation,
    #[serde(flatten)]
    pub output: FunctionOutputValidation,
}
