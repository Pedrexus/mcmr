#[derive(Clone, Copy)]
pub(super) enum DeclarationKind {
    Attribute,
    Class,
    Function,
    Method,
    Property,
    Variable,
}

impl DeclarationKind {
    pub(super) fn as_str(self) -> &'static str {
        match self {
            Self::Attribute => "attribute",
            Self::Class => "class",
            Self::Function => "function",
            Self::Method => "method",
            Self::Property => "property",
            Self::Variable => "variable",
        }
    }
}
