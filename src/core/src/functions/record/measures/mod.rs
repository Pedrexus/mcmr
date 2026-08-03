use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionMeasures {
    pub reference_count: usize,
    pub behavior_operation_count: usize,
    pub conditional_count: usize,
    pub gather_consumes_created_tasks: bool,
    pub gather_returns_exceptions: bool,
    pub has_task_group: bool,
    pub reads_receiver: bool,
}
