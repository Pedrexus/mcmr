#[derive(Clone, Copy)]
pub(super) struct FactIdentity<'fact> {
    pub(super) key: &'fact str,
    pub(super) path: &'fact str,
}

impl FactIdentity<'_> {
    pub(super) fn base(self) -> serde_json::Value {
        serde_json::json!({
            "key": self.key,
            "span": {"path": self.path},
            "language": "python",
        })
    }
}
