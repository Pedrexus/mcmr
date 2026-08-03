/// Scope evidence used to resolve one graph reference.
pub struct ReferenceResolution {
    pub owner: Option<String>,
    pub receiver_type: Option<String>,
    pub binding_count: usize,
}
