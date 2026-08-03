use serde_json::Value;

/// Every borrow, pin, and copy one module states while it is walked.
#[derive(Default)]
pub(super) struct Surface {
    pub(super) owners: Vec<String>,
    pub(super) loop_depth: usize,
    pub(super) demanding: bool,
    pub(super) annotations: Vec<Value>,
    pub(super) pins: Vec<Value>,
    pub(super) clones: Vec<Value>,
}
