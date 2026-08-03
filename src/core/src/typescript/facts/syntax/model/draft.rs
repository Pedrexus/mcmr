use super::node::SyntaxNode;
use super::semantic::SyntaxSemantic;
use crate::source::Source;
use oxc_span::Span;
use serde_json::Value;

/// One semantic node waiting for the visitor to finish all children inside it.
pub(in crate::typescript::facts::syntax) struct SyntaxDraft {
    pub(in crate::typescript::facts::syntax) kind: SyntaxSemantic,
    pub(in crate::typescript::facts::syntax) name: String,
    pub(in crate::typescript::facts::syntax) span: Span,
    pub(in crate::typescript::facts::syntax) children: Vec<SyntaxDraft>,
}

impl SyntaxDraft {
    pub(in crate::typescript::facts::syntax) fn new(
        kind: SyntaxSemantic,
        name: String,
        span: Span,
    ) -> Self {
        Self {
            kind,
            name,
            span,
            children: Vec::new(),
        }
    }

    pub(in crate::typescript::facts::syntax) fn value(self, source: &Source) -> Value {
        let children = self
            .children
            .into_iter()
            .map(|child| child.value(source))
            .collect();
        SyntaxNode {
            children,
            kind: self.kind,
            name: self.name,
            span: self.span,
        }
        .value(source)
    }
}
