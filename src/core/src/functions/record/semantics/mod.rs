use serde::Serialize;

mod outcomes;
mod roles;

pub use outcomes::FunctionOutcomes;
pub use roles::FunctionRoles;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionSemantics {
    #[serde(flatten)]
    pub roles: FunctionRoles,
    #[serde(flatten)]
    pub outcomes: FunctionOutcomes,
}
