use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionOutcomes {
    pub is_protocol_member: bool,
    pub is_overload: bool,
    pub is_property: bool,
    pub is_framework_hook: bool,
    pub is_declarative_body: bool,
    pub is_polymorphic: bool,
    pub is_pass_body: bool,
}
