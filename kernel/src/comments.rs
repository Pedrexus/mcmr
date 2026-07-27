use crate::source::Source;
use ruff_text_size::{TextRange, TextSize};
use serde_json::{Value, json};

/// What one language has to say about its own comments, past what every language shares.
///
/// Grouping, sizing, and addressing are the same wherever a comment appears, so they are settled
/// here once. Whether a comment speaks to a tool and whether it is code rather than prose are not,
/// because both are answered by reading the language, so each frontend states those two and shares
/// everything else. A rule then reads one family and cannot tell which frontend answered.
pub trait Dialect {
    /// Whether one comment body speaks to a tool rather than to a reader.
    fn is_directive(&mut self, body: &str) -> bool;

    /// Whether one comment body is source this language would compile rather than prose.
    fn is_source(&mut self, body: &str) -> bool;
}

/// Whether one comment body opens with any of the words a language reserves for its tools.
///
/// Every suppression, formatter switch, and coverage marker is written as the first word of the
/// comment, so matching the opening is what keeps a sentence that merely mentions one from
/// reading as a directive.
pub fn opens_with(body: &str, markers: &[&str]) -> bool {
    let lowered = body.to_ascii_lowercase();
    markers.iter().any(|marker| lowered.starts_with(marker))
}

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

/// Return what one comment says, without the markers that made it a comment.
///
/// The slash languages spell one comment six ways between them, and a rule reading the family
/// cares about the sentence rather than about which of the six a file used. Only the markers and
/// the space after them come off, because a commented-out block is recognized by parsing what it
/// says and a block whose shape was trimmed away cannot parse.
pub fn body(text: &str) -> String {
    let Some(inner) = text.strip_prefix("/*") else {
        let opened = text.trim_start_matches('/');
        return opened
            .strip_prefix('!')
            .unwrap_or(opened)
            .trim()
            .to_string();
    };
    inner
        .trim_end_matches("*/")
        .lines()
        .map(|line| line.trim().trim_start_matches('*').trim_start())
        .collect::<Vec<_>>()
        .join("\n")
        .trim()
        .to_string()
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
        let opened = source.line_of(range.start());
        let directive = dialect.is_directive(&body(text));
        match current.as_mut() {
            Some(group) if group.follows(opened, directive) => group.absorb(source, range, text),
            _ => {
                let mut started = Group::new(directive);
                started.absorb(source, range, text);
                if let Some(group) = current.replace(started) {
                    groups.push(group.value(source, dialect));
                }
            }
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

/// Locate one comment from the byte offsets its reader found it at.
pub fn at(start: usize, end: usize) -> TextRange {
    TextRange::new(TextSize::new(start as u32), TextSize::new(end as u32))
}

/// One run of comment lines that sit directly above one another.
struct Group {
    last_line: usize,
    line_count: usize,
    character_count: usize,
    token_count: usize,
    body: String,
    is_directive: bool,
    range: TextRange,
}

impl Group {
    fn new(is_directive: bool) -> Self {
        Self {
            last_line: 0,
            line_count: 0,
            character_count: 0,
            token_count: 0,
            body: String::new(),
            is_directive,
            range: TextRange::default(),
        }
    }

    /// Whether one comment continues this group, which it does by sitting on the very next line.
    ///
    /// A directive and a sentence never join, even when they are adjacent, because the rules read
    /// the two for opposite reasons and a suppression absorbed into a paragraph would hide both.
    fn follows(&self, opened: usize, is_directive: bool) -> bool {
        self.last_line + 1 == opened && self.is_directive == is_directive
    }

    fn absorb(&mut self, source: &Source, range: TextRange, text: &str) {
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

    fn value(&self, source: &Source, dialect: &mut impl Dialect) -> Value {
        json!({
            "line_count": self.line_count,
            "character_count": self.character_count,
            "token_count": self.token_count,
            "parses_as_source": !self.is_directive && dialect.is_source(self.body.trim()),
            "is_directive": self.is_directive,
            "node": source.node("comment", self.range),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// One dialect that calls a marked comment a directive and a braced one source.
    struct Fixture;

    impl Dialect for Fixture {
        fn is_directive(&mut self, body: &str) -> bool {
            opens_with(body, &["nolint"])
        }

        fn is_source(&mut self, body: &str) -> bool {
            holds_code(body, &[';'])
        }
    }

    fn groups_of(text: &str, found: Vec<TextRange>) -> Vec<Value> {
        let source = Source::new("src/example.rs", text);
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
        let groups = groups_of(text, vec![at(0, 8), at(9, 18), at(20, 28)]);

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0]["line_count"], 2);
        assert_eq!(groups[0]["token_count"], 4);
        assert_eq!(groups[1]["line_count"], 1);
    }

    #[test]
    fn a_directive_never_joins_the_sentence_next_to_it() {
        let text = "// NOLINT\n// a sentence\n";
        let groups = groups_of(text, vec![at(0, 9), at(10, 23)]);

        assert_eq!(groups.len(), 2);
        assert_eq!(groups[0]["is_directive"], true);
        assert_eq!(groups[0]["parses_as_source"], false);
        assert_eq!(groups[1]["is_directive"], false);
    }

    #[test]
    fn a_block_comment_counts_every_line_it_covers() {
        let text = "/* one\n   two\n   three */\n// joined\n";
        let groups = groups_of(text, vec![at(0, 25), at(26, 35)]);

        assert_eq!(groups.len(), 1);
        assert_eq!(groups[0]["line_count"], 4);
        assert_eq!(groups[0]["node"]["kind"], "comment");
    }

    #[test]
    fn a_group_is_addressed_across_every_comment_it_holds() {
        let text = "// let value = 1;\n// more\n";
        let groups = groups_of(text, vec![at(0, 17), at(18, 25)]);

        assert_eq!(groups[0]["parses_as_source"], true);
        assert_eq!(groups[0]["node"]["span"]["start_line"], 1);
        assert_eq!(groups[0]["node"]["span"]["end_line"], 2);
    }

    #[test]
    fn a_document_stating_no_comment_still_answers_the_family() {
        let source = Source::new("src/example.rs", "fn run() {}\n");
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
        assert!(opens_with("NOLINT next line", &["nolint"]));
        assert!(!opens_with("the nolint marker", &["nolint"]));
    }
}
