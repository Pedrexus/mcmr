use crate::protocol::JsonObject;
use crate::source::Source;
use ruff_python_ast::token::{TokenKind, Tokens};
use ruff_python_parser::parse_module;
use ruff_text_size::Ranged;
use serde_json::{Value, json};

use super::fact::base;

/// One run of comment lines that sit directly above one another.
#[derive(Default)]
struct CommentGroup {
    last_line: usize,
    line_count: usize,
    character_count: usize,
    token_count: usize,
    body: String,
    is_directive: bool,
    range: ruff_text_size::TextRange,
}

impl CommentGroup {
    fn start(line: usize, text: &str, range: ruff_text_size::TextRange) -> Self {
        let mut group = Self {
            last_line: line,
            is_directive: is_directive(text),
            range,
            ..Self::default()
        };
        group.absorb(line, text, range);
        group
    }

    fn absorb(&mut self, line: usize, text: &str, range: ruff_text_size::TextRange) {
        self.range = ruff_text_size::TextRange::new(self.range.start(), range.end());
        self.last_line = line;
        self.line_count += 1;
        self.character_count += text.len();
        self.token_count += text.split_whitespace().count();
        if !self.body.is_empty() {
            self.body.push('\n');
        }
        self.body.push_str(comment_body(text));
    }

    fn value(&self, source: &Source) -> Value {
        let (preceding_source, following_source) = source.neighbors(self.range, 3);
        json!({
            "text": self.body,
            "preceding_source": preceding_source,
            "following_source": following_source,
            "line_count": self.line_count,
            "character_count": self.character_count,
            "token_count": self.token_count,
            "parses_as_source": !self.is_directive && parses_as_statement(self.body.trim()),
            "is_directive": self.is_directive,
            "is_documentation": false,
            "node": source.node("comment", self.range),
        })
    }
}

pub(super) fn comment_fact(source: &Source, tokens: &Tokens) -> Value {
    let mut groups: Vec<Value> = Vec::new();
    let mut current: Option<CommentGroup> = None;
    for token in tokens
        .iter()
        .filter(|token| token.kind() == TokenKind::Comment)
    {
        let text = source.slice(token.range());
        let line = source.line_of(token.range().start());
        match current.as_mut() {
            Some(group)
                if group.last_line + 1 == line && group.is_directive == is_directive(text) =>
            {
                group.absorb(line, text, token.range());
            }
            _ => {
                let started = CommentGroup::start(line, text, token.range());
                if let Some(group) = current.replace(started) {
                    groups.push(group.value(source));
                }
            }
        }
    }
    if let Some(group) = current {
        groups.push(group.value(source));
    }
    let key = format!("comments:{}", source.relative);
    JsonObject::new(base(source, &key, ruff_text_size::TextRange::default()))
        .merged(json!({"groups": groups}))
}

/// Return what one comment line says, without the marker that made it a comment.
///
/// Only the marker and the single space after it are removed. A commented-out block is recognized
/// by parsing what it says, and a block whose indentation was trimmed away cannot parse, so the
/// one rule that finds commented-out code depends on keeping the shape of the lines intact.
pub(super) fn comment_body(text: &str) -> &str {
    let body = text.trim_start_matches('#');
    body.strip_prefix(' ').unwrap_or(body).trim_end()
}

fn is_directive(text: &str) -> bool {
    let body = comment_body(text).to_ascii_lowercase();
    [
        "noqa", "type:", "pragma", "ruff:", "mypy:", "pyright:", "fmt:", "isort:",
    ]
    .iter()
    .any(|marker| body.starts_with(marker))
}

/// Whether one comment body is source rather than prose, decided by parsing it.
fn parses_as_statement(text: &str) -> bool {
    !text.is_empty() && text.contains(['=', '(', ':']) && parse_module(text).is_ok()
}
