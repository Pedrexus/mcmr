use crate::protocol::{Node, Span};
use ruff_source_file::LineIndex;
use ruff_text_size::{Ranged, TextRange, TextSize};

/// One document and the indexes every extractor reads positions through.
///
/// The source is owned rather than borrowed. One copy per file is far cheaper than the parse that
/// follows it, and it keeps every extractor signature free of a lifetime it would only be
/// threading through.
pub struct Source {
    pub relative: String,
    pub text: String,
    pub lines: LineIndex,
}

impl Source {
    pub fn new(relative: &str, text: &str) -> Self {
        Self {
            relative: relative.to_string(),
            text: text.to_string(),
            lines: LineIndex::from_source_text(text),
        }
    }

    /// Return the span one range covers, in the shape the Python models validate.
    pub fn span(&self, range: TextRange) -> Span {
        let start = self.lines.line_column(range.start(), &self.text);
        let end = self.lines.line_column(range.end(), &self.text);
        Span {
            path: self.relative.clone(),
            start_line: start.line.get(),
            start_column: start.column.get().saturating_sub(1),
            end_line: end.line.get(),
            end_column: end.column.get().saturating_sub(1),
        }
    }

    /// Return the exact source one range covers.
    pub fn slice(&self, range: TextRange) -> &str {
        &self.text[usize::from(range.start())..usize::from(range.end())]
    }

    /// Address one node so a fix can name it without recomputing a byte range.
    pub fn node(&self, kind: &str, range: TextRange) -> Node {
        Node {
            id: format!("{}:{}:{}", self.relative, u32::from(range.start()), kind),
            span: self.span(range),
            kind: kind.to_string(),
            text: self.slice(range).to_string(),
        }
    }

    /// Address one node from any element that carries a range.
    pub fn node_of(&self, kind: &str, ranged: &impl Ranged) -> Node {
        self.node(kind, ranged.range())
    }

    /// Return how many lines one range spans.
    pub fn line_count(&self, range: TextRange) -> usize {
        let start = self.lines.line_column(range.start(), &self.text).line.get();
        let end = self.lines.line_column(range.end(), &self.text).line.get();
        end.saturating_sub(start) + 1
    }

    /// Return the line a byte offset sits on.
    pub fn line_of(&self, offset: TextSize) -> usize {
        self.lines.line_column(offset, &self.text).line.get()
    }
}
