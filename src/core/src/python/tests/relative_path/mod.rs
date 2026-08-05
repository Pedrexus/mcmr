#[derive(Clone, Copy)]
pub(super) struct RelativePath<Path: AsRef<str>>(pub(super) Path);
