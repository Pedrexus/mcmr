#[derive(Clone, Copy)]
pub(super) enum AnnotationRole {
    Variable,
    Alias,
    Return,
    Parameter,
}

impl AnnotationRole {
    pub(super) fn as_str(self) -> &'static str {
        match self {
            Self::Variable => "variable",
            Self::Alias => "alias",
            Self::Return => "return",
            Self::Parameter => "parameter",
        }
    }
}
