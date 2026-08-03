use crate::source::Source;
use ruff_text_size::{TextRange, TextSize};
use serde_json::{Value, json};
use std::ops::Range;

mod dialect;
mod group;
mod kind;
mod text;

pub use dialect::Dialect;
use group::Group;
use kind::CommentKind;
pub use text::CommentText;
use text::body;

/// Whether one comment body holds any of the punctuation its language cannot state code without.
///
/// A parser is generous with a single bare word, so `// retry` would come back as a valid
/// expression and every one-word note would read as commented-out code. Asking first whether the
/// body even holds the punctuation a statement needs separates a line of source from a line of
/// prose, and it keeps the parser off the prose that makes up most comments, which is what the
/// family costs almost all of its time on.
///
/// Which punctuation counts is the language's own answer rather than a shared one. A brace
/// language ends every statement, so a note holding neither a semicolon nor a brace is prose. A
/// language whose blocks yield their last expression cannot say that, because the expression is
/// the statement.
pub fn holds_code(body: &str, punctuation: &[char]) -> bool {
    !body.is_empty() && body.contains(punctuation)
}

/// Build the comment family's one fact for a document from the comments it states.
///
/// The comments arrive in source order and already located, because finding them is the one part
/// no shared reader can do: a tree-sitter grammar hands them over as nodes where `syn` drops them
/// and only a lexical scan sees them at all.
pub fn fact(
    source: &Source,
    language: &str,
    found: impl IntoIterator<Item = TextRange>,
    dialect: &mut impl Dialect,
) -> Value {
    let mut groups: Vec<Value> = Vec::new();
    let mut current: Option<Group> = None;
    for range in found {
        let text = source.slice(range);
        let kind = if dialect.is_directive(&body(text)) {
            CommentKind::directive(text)
        } else {
            CommentKind::ordinary(text)
        };
        if let Some(group) = absorb_group(source, range, kind, &mut current) {
            groups.push(group.value(source, dialect));
        }
    }
    if let Some(group) = current {
        groups.push(group.value(source, dialect));
    }
    json!({
        "key": format!("comments:{}", source.relative),
        "span": source.span(TextRange::default()),
        "language": language,
        "groups": groups,
    })
}

fn absorb_group(
    source: &Source,
    range: TextRange,
    kind: CommentKind,
    current: &mut Option<Group>,
) -> Option<Group> {
    let opened = source.line_of(range.start());
    let text = source.slice(range);
    if let Some(group) = current.as_mut()
        && group.follows(opened, kind)
    {
        group.absorb(source, range, text);
        return None;
    }
    let mut started = Group::new(kind);
    started.absorb(source, range, text);
    current.replace(started)
}

/// Locate one comment from the byte offsets its reader found it at.
pub fn at(range: Range<usize>) -> TextRange {
    TextRange::new(
        TextSize::new(range.start as u32),
        TextSize::new(range.end as u32),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    /// One dialect that calls a marked comment a directive and a braced one source.
    struct Fixture;

    impl Dialect for Fixture {
        fn is_directive(&mut self, body: &str) -> bool {
            body.opens_with(&["nolint"])
        }

        fn is_source(&mut self, body: &str) -> bool {
            holds_code(body, &[';'])
        }
    }

    fn groups_of(text: &str, found: Vec<TextRange>) -> Vec<Value> {
        let document = crate::discovery::Document {
            relative: "src/example.rs".to_string(),
            source: text.to_string(),
        };
        let source = Source::new(&document);
        let built = fact(&source, "rust", found, &mut Fixture);
        built["groups"].as_array().cloned().unwrap_or_default()
    }

    #[test]
    fn every_marker_this_family_of_languages_writes_comes_off_the_body() {
        assert_eq!(body("// plain"), "plain");
        assert_eq!(body("/// documented"), "documented");
        assert_eq!(body("//! owned by the module"), "owned by the module");
        assert_eq!(body("/* held */"), "held");
        assert_eq!(
            body("/**\n * over two lines\n * of prose\n */"),
            "over two lines\nof prose"
        );
    }

    #[test]
    fn lines_that_sit_together_are_one_group_and_a_gap_starts_another() {
        let text = "// first\n// second\n\n// apart\n";
        let groups = groups_of(text, vec![at(0..8), at(9..18), at(20..28)]);

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0]["line_count"], 2);
        assert_eq!(groups[0]["token_count"], 4);
        assert_eq!(groups[0]["text"], "first\nsecond");
        assert_eq!(groups[0]["following_source"], "\n// apart");
        assert_eq!(groups[1]["line_count"], 1);
    }

    #[test]
    fn a_directive_never_joins_the_sentence_next_to_it() {
        let text = "// NOLINT\n// a sentence\n";
        let groups = groups_of(text, vec![at(0..9), at(10..23)]);

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0]["is_directive"], true);
        assert_eq!(groups[0]["parses_as_source"], false);
        assert_eq!(groups[1]["is_directive"], false);
    }

    #[test]
    fn documentation_never_joins_an_adjacent_implementation_comment() {
        let text = "/// Public contract\n// Retry because the peer closes idle sockets\n";
        let groups = groups_of(text, vec![at(0..19), at(20..63)]);

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0]["is_documentation"], true);
        assert_eq!(groups[1]["is_documentation"], false);
    }

    #[test]
    fn a_block_comment_counts_every_line_it_covers() {
        let text = "/* one\n   two\n   three */\n// joined\n";
        let groups = groups_of(text, vec![at(0..25), at(26..35)]);

        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0]["line_count"], 4);
        assert_eq!(groups[0]["node"]["kind"], "comment");
    }

    #[test]
    fn a_group_is_addressed_across_every_comment_it_holds() {
        let text = "// let value = 1;\n// more\n";
        let groups = groups_of(text, vec![at(0..17), at(18..25)]);

        assert_eq!(groups[0]["parses_as_source"], true);
        assert_eq!(groups[0]["node"]["span"]["start_line"], 1);
        assert_eq!(groups[0]["node"]["span"]["end_line"], 2);
    }

    #[test]
    fn a_document_stating_no_comment_still_answers_the_family() {
        let document = crate::discovery::Document {
            relative: "src/example.rs".to_string(),
            source: "fn run() {}\n".to_string(),
        };
        let source = Source::new(&document);
        let built = fact(&source, "rust", Vec::new(), &mut Fixture);

        assert_eq!(built["key"], "comments:src/example.rs");
        assert_eq!(built["language"], "rust");
        assert!(built["groups"].as_array().unwrap().is_empty());
    }

    #[test]
    fn prose_is_never_handed_to_a_parser_and_punctuation_always_is() {
        assert!(!holds_code("", &[';']));
        assert!(!holds_code("retry twice before giving up", &[';']));
        assert!(holds_code("let value = 1;", &[';']));
        assert!(!holds_code("read(name)", &[';', '{']));
        assert!(holds_code("read(name)", &['(', ';']));
        assert!("NOLINT next line".opens_with(&["nolint"]));
        assert!(!"the nolint marker".opens_with(&["nolint"]));
    }
}
