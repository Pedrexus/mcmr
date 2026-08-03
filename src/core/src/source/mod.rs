use crate::discovery::Document;
use crate::protocol::{Node, Span};
use proc_macro2::LineColumn;
use ruff_source_file::{LineIndex, OneIndexed};
use ruff_text_size::{Ranged, TextRange, TextSize};
use std::ops::Range;

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

/// Whether one path follows a repository test-file convention.
pub fn is_test_path(path: &str) -> bool {
    let mut parts = path.split('/');
    let file = parts.next_back().unwrap_or(path);
    file.starts_with("test_")
        || matches!(file, "test.py" | "tests.py" | "tests.rs" | "conftest.py")
        || ["_test.", ".test.", ".spec."]
            .iter()
            .any(|marker| file.contains(marker))
        || parts.any(|part| matches!(part, "test" | "tests" | "__tests__"))
}

impl Source {
    pub fn new(document: &Document) -> Self {
        Self {
            relative: document.relative.clone(),
            text: document.source.clone(),
            lines: LineIndex::from_source_text(&document.source),
        }
    }

    /// Return how many lines one range spans.
    pub fn line_count(&self, range: TextRange) -> usize {
        let start = self.lines.line_column(range.start(), &self.text).line.get();
        let end = self.lines.line_column(range.end(), &self.text).line.get();
        end.checked_sub(start)
            .expect("a source range cannot end before it starts")
            + 1
    }

    /// Return the line a byte offset sits on.
    pub fn line_of(&self, offset: TextSize) -> usize {
        self.lines.line_column(offset, &self.text).line.get()
    }

    /// Return bounded source immediately before and after one range.
    pub fn neighbors(&self, range: TextRange, line_limit: usize) -> (String, String) {
        let lines: Vec<&str> = self.text.lines().collect();
        let start = self.line_of(range.start()).saturating_sub(1);
        let end = self.line_of(range.end()).min(lines.len());
        let before = lines[start.saturating_sub(line_limit)..start].join("\n");
        let after = lines[end..(end + line_limit).min(lines.len())].join("\n");
        (before, after)
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

    /// Return the byte range covered by one-based lines and zero-based byte columns.
    pub fn range_location(&self, location: Range<LineColumn>) -> TextRange {
        let start_line = OneIndexed::new(location.start.line).expect("a source line is one based");
        let end_line = OneIndexed::new(location.end.line).expect("a source line is one based");
        let start = self.lines.line_start(start_line, &self.text)
            + TextSize::try_from(location.start.column)
                .expect("a source column fits the text index");
        let end = self.lines.line_start(end_line, &self.text)
            + TextSize::try_from(location.end.column)
                .expect("a source column fits the text index");
        TextRange::new(start, end)
    }

    /// Return the exact source one range covers.
    pub fn slice(&self, range: TextRange) -> &str {
        &self.text[usize::from(range.start())..usize::from(range.end())]
    }

    /// Return the exact source covered by one-based lines and zero-based byte columns.
    pub fn slice_location(&self, location: Range<LineColumn>) -> &str {
        self.slice(self.range_location(location))
    }

    /// Return the span one range covers, in the shape the Python models validate.
    pub fn span(&self, range: TextRange) -> Span {
        let start = self.lines.line_column(range.start(), &self.text);
        let end = self.lines.line_column(range.end(), &self.text);
        let start_column = range.start() - self.lines.line_start(start.line, &self.text);
        let end_column = range.end() - self.lines.line_start(end.line, &self.text);
        Span {
            path: self.relative.clone(),
            start_line: start.line.get(),
            start_column: usize::from(start_column),
            end_line: end.line.get(),
            end_column: usize::from(end_column),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn spans_and_slices_use_utf8_byte_columns() {
        let text = "let café = value;\n";
        let document = Document {
            relative: "src/example.rs".to_string(),
            source: text.to_string(),
        };
        let source = Source::new(&document);
        let start = TextSize::try_from(text.find("value").expect("the name is present"))
            .expect("the offset fits");
        let end = start + TextSize::new(5);
        let span = source.span(TextRange::new(start, end));

        assert_eq!((span.start_column, span.end_column), (12, 17));
        assert_eq!(
            source.slice_location(
                LineColumn {
                    line: 1,
                    column: 12
                }..LineColumn {
                    line: 1,
                    column: 17,
                }
            ),
            "value"
        );
    }

    #[test]
    fn neighboring_source_excludes_the_addressed_range_and_stays_bounded() {
        let text = "before one\nbefore two\n# note\nafter one\nafter two\n";
        let document = Document {
            relative: "src/example.py".to_string(),
            source: text.to_string(),
        };
        let source = Source::new(&document);
        let start = TextSize::try_from(text.find("# note").expect("the note exists"))
            .expect("the offset fits");
        let end = start + TextSize::new(6);

        assert_eq!(
            source.neighbors(TextRange::new(start, end), 1),
            ("before two".to_string(), "after one".to_string())
        );
    }

    #[test]
    fn test_paths_follow_language_runner_conventions_without_claiming_testing_packages() {
        for path in [
            "tests/test_engine.py",
            "src/conftest.py",
            "src/engine_test.rs",
            "src/parser/tests.rs",
            "web/engine.spec.ts",
            "src/__tests__/engine.ts",
        ] {
            assert!(is_test_path(path), "{path}");
        }
        assert!(!is_test_path("src/engine.py"));
        assert!(!is_test_path("src/rules/testing/relations.py"));
    }
}
