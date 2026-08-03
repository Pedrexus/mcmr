use crate::comments;
use crate::comments::CommentText as _;
use oxc_allocator::Allocator;
use oxc_parser::Parser;
use oxc_span::SourceType;

/// Interpret TypeScript comments after the shared reader locates them.
pub(super) struct Notes {
    pub(super) relative: String,
}

impl comments::Dialect for Notes {
    fn is_directive(&mut self, body: &str) -> bool {
        body.opens_with(&[
            "@ts-ignore",
            "@ts-expect-error",
            "eslint",
            "prettier-ignore",
            "istanbul ignore",
            "c8 ignore",
            "biome-ignore",
            "deno-lint-ignore",
            "oxlint-disable",
        ])
    }

    fn is_source(&mut self, body: &str) -> bool {
        comments::holds_code(body, &['=', '(', ';', '{'])
            && (self.parses(&format!("function mcmrProbe() {{\n{body}\n}}")) || self.parses(body))
    }
}

impl Notes {
    fn parses(&self, text: &str) -> bool {
        let allocator = Allocator::default();
        let kind = SourceType::from_path(&self.relative)
            .expect("a TypeScript comment must retain its source suffix");
        let parsed = Parser::new(&allocator, text, kind).parse();
        !parsed.panicked && parsed.diagnostics.is_empty()
    }
}
