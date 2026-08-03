/// Distinguish prose, documentation, and tool directives without positional Boolean flags.
#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum CommentKind {
    Ordinary,
    Directive,
    Documentation,
    DocumentDirective,
}

impl CommentKind {
    pub(super) fn directive(text: &str) -> Self {
        if Self::is_documented(text) {
            Self::DocumentDirective
        } else {
            Self::Directive
        }
    }

    pub(super) fn ordinary(text: &str) -> Self {
        if Self::is_documented(text) {
            Self::Documentation
        } else {
            Self::Ordinary
        }
    }

    pub(super) fn is_directive(self) -> bool {
        matches!(self, Self::Directive | Self::DocumentDirective)
    }

    pub(super) fn is_documentation(self) -> bool {
        matches!(self, Self::Documentation | Self::DocumentDirective)
    }

    fn is_documented(text: &str) -> bool {
        ["///", "//!", "/**", "/*!"]
            .iter()
            .any(|marker| text.starts_with(marker))
    }
}
