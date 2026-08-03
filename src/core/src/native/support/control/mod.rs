use crate::functions::ControlIncrement;

/// Every control structure one body states at its visible nesting depth.
#[derive(Default)]
pub(super) struct Control {
    pub(super) depth: usize,
    pub(super) increments: Vec<ControlIncrement>,
}
