use super::{dialect::Dialect, kind::CommentKind, text::body};
use crate::source::Source;
use ruff_text_size::TextRange;
use serde_json::{Value, json};

/// One run of comment lines that sit directly above one another.
pub(super) struct Group {
    last_line: usize,
    line_count: usize,
    character_count: usize,
    token_count: usize,
    body: String,
    kind: CommentKind,
    range: TextRange,
}

impl Group {
    pub(super) fn new(kind: CommentKind) -> Self {
        Self {
            last_line: 0,
            line_count: 0,
            character_count: 0,
            token_count: 0,
            body: String::new(),
            kind,
            range: TextRange::default(),
        }
    }

    pub(super) fn absorb(&mut self, source: &Source, range: TextRange, text: &str) {
        self.range = match self.line_count {
            0 => range,
            _ => TextRange::new(self.range.start(), range.end()),
        };
        self.last_line = source.line_of(range.end());
        self.line_count += source.line_count(range);
        self.character_count += text.len();
        self.token_count += text.split_whitespace().count();
        if !self.body.is_empty() {
            self.body.push('\n');
        }
        self.body.push_str(&body(text));
    }

    /// Whether one comment continues this group, which it does by sitting on the very next line.
    ///
    /// A directive and a sentence never join, even when they are adjacent, because the rules read
    /// the two for opposite reasons and a suppression absorbed into a paragraph would hide both.
    pub(super) fn follows(&self, opened: usize, kind: CommentKind) -> bool {
        self.last_line + 1 == opened && self.kind == kind
    }

    pub(super) fn value(&self, source: &Source, dialect: &mut impl Dialect) -> Value {
        let (preceding_source, following_source) = source.neighbors(self.range, 3);
        json!({
            "text": self.body,
            "preceding_source": preceding_source,
            "following_source": following_source,
            "line_count": self.line_count,
            "character_count": self.character_count,
            "token_count": self.token_count,
            "parses_as_source": !self.kind.is_directive() && dialect.is_source(self.body.trim()),
            "is_directive": self.kind.is_directive(),
            "is_documentation": self.kind.is_documentation(),
            "node": source.node("comment", self.range),
        })
    }
}
