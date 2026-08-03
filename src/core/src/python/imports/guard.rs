#[derive(Clone, Copy)]
pub(super) enum ImportGuard {
    Unguarded,
    Guarded,
}

impl ImportGuard {
    pub(super) fn is_guarded(self) -> bool {
        matches!(self, Self::Guarded)
    }
}
