use super::super::{control::ControlIncrement, parameter::FunctionParameter};
use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionStructure {
    pub control_increments: Vec<ControlIncrement>,
    pub parameters: Vec<FunctionParameter>,
    pub decorators: Vec<String>,
    pub recognized_tensor_roles: Vec<String>,
    pub created_task_count: usize,
    pub implementation_lines: usize,
    pub direct_statement_count: usize,
}
