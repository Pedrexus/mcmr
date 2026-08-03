use super::parsing::grammar;
use crate::comments;
use crate::comments::CommentText as _;
use tree_sitter::Parser;

/// What C, C++, and CUDA say about their own comments, past what the shared reader settles.
///
/// The parser is held across the whole document rather than built per comment, because deciding
/// whether a comment is code means parsing it and a header states hundreds of them.
pub(super) struct Notes {
    parser: Parser,
}

impl Notes {
    pub(super) fn of(relative: &str) -> Self {
        let mut parser = Parser::new();
        parser
            .set_language(&grammar(relative))
            .expect("the selected native grammar must load");
        Self { parser }
    }

    /// Whether one fragment is something this dialect would accept as written.
    fn compiles(&mut self, text: &str) -> bool {
        self.parser
            .parse(text, None)
            .is_some_and(|tree| !tree.root_node().has_error())
    }
}

impl comments::Dialect for Notes {
    /// Whether one comment addresses a tool rather than a reader.
    ///
    /// These are the switches the tools around the compiler read out of a comment, since the
    /// language itself has no way to state one. All of them open the comment they sit in.
    fn is_directive(&mut self, body: &str) -> bool {
        body.opens_with(&[
            "nolint",
            "clang-format",
            "cppcheck-suppress",
            "iwyu pragma",
            "coverity",
            "lcov_excl",
            "codecov",
            "cspell",
            "nosonar",
        ])
    }

    /// Whether one comment body is source this dialect would compile rather than prose.
    ///
    /// A function body is tried first and a translation unit second, because a commented-out
    /// statement is far and away the common case and settling it takes one parse. A declaration
    /// needs the second, since this language does not let one sit inside a body.
    ///
    /// Every statement this language has ends in a semicolon or opens a brace, so a note holding
    /// neither is prose and never reaches the parser at all.
    fn is_source(&mut self, body: &str) -> bool {
        comments::holds_code(body, &[';', '{'])
            && (self.compiles(&format!("void mcmr_probe() {{\n{body}\n}}")) || self.compiles(body))
    }
}
