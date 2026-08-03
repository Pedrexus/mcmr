use super::semantic::SyntaxSemantic;
use crate::source::Source;
use crate::typescript::support::range;
use oxc_span::Span;
use serde_json::{Value, json};

pub(in crate::typescript::facts::syntax) struct SyntaxNode {
    pub(in crate::typescript::facts::syntax) children: Vec<Value>,
    pub(in crate::typescript::facts::syntax) kind: SyntaxSemantic,
    pub(in crate::typescript::facts::syntax) name: String,
    pub(in crate::typescript::facts::syntax) span: Span,
}

impl SyntaxNode {
    pub(in crate::typescript::facts::syntax) fn value(self, source: &Source) -> Value {
        json!({
            "kind": self.kind,
            "name": self.name,
            "span": source.span(range(self.span)),
            "children": self.children,
        })
    }
}
