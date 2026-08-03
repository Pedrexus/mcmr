use serde::Serialize;

mod contract;

pub use contract::ParameterContract;

/// One parameter in the call contract shared by every language frontend.
#[derive(Clone, Debug, Serialize)]
pub struct FunctionParameter {
    pub name: String,
    pub type_name: String,
    #[serde(flatten)]
    pub contract: ParameterContract,
}

impl FunctionParameter {
    pub fn named(name: String) -> Self {
        Self {
            name,
            type_name: String::new(),
            contract: ParameterContract::default(),
        }
    }
}
