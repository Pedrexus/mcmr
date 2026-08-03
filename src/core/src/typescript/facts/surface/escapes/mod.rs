use self::collector::Hatches;
use self::kind::TypeEscapeKind;
use crate::source::Source;
use crate::typescript::support::range;
use oxc_ast::ast::Program;
use oxc_ast_visit::Visit;
use serde_json::{Value, json};

mod collector;
mod kind;

/// Return parsed type escapes and explicit checker suppressions.
pub(super) fn escape_hatches(source: &Source, program: &Program) -> Vec<Value> {
    let mut found = Hatches::default();
    found.visit_program(program);
    found.found.extend(comment_hatches(source, program));
    found.found.sort_by_key(|(_, span)| span.start);
    render(source, &found.found)
}

fn comment_hatches<'a>(
    source: &'a Source,
    program: &'a Program<'a>,
) -> impl Iterator<Item = (TypeEscapeKind, oxc_span::Span)> + 'a {
    program
        .comments
        .iter()
        .filter(|comment| suppresses(source.slice(range(comment.span))))
        .map(|comment| (TypeEscapeKind::IgnoreComment, comment.span))
}

fn render(source: &Source, found: &[(TypeEscapeKind, oxc_span::Span)]) -> Vec<Value> {
    found
        .iter()
        .map(|(kind, span)| {
            json!({
                "kind": kind.as_str(),
                "line": source.line_of(range(*span).start()),
            })
        })
        .collect()
}

/// Whether one comment turns the type checker off rather than saying something to a reader.
fn suppresses(text: &str) -> bool {
    text.contains("@ts-ignore") || text.contains("@ts-expect-error")
}
