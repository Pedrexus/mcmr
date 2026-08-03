#[derive(Clone, Copy)]
pub(super) enum TypeEscapeKind {
    Assertion,
    NonNull,
    Any,
    IgnoreComment,
}

impl TypeEscapeKind {
    pub(super) fn as_str(self) -> &'static str {
        match self {
            Self::Assertion => "assertion",
            Self::NonNull => "non_null",
            Self::Any => "any",
            Self::IgnoreComment => "ignore_comment",
        }
    }
}
