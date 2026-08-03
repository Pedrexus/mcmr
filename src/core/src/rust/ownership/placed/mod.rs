/// Every signature position in which a lifetime occurs.
#[derive(Default)]
pub(super) struct Placed {
    pub(super) returned: Vec<String>,
    pub(super) receiver: String,
    pub(super) parameters: Vec<String>,
    pub(super) beyond: Vec<String>,
    pub(super) required_by_syntax: Vec<String>,
}
