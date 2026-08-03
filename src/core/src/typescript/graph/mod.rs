use crate::graph::Stated;
use crate::source::Source;
use collector::Collector;
use oxc_allocator::Allocator;
use oxc_ast_visit::Visit;
use oxc_parser::Parser;
use oxc_span::SourceType;

pub use paths::{Located, Specifiers, WrittenSpecifier};
#[cfg(test)]
pub(in crate::typescript) use paths::{mappings_at, parse_config};
pub use resolution::{ResolutionContext, resolve};

mod collector;
mod paths;
mod resolution;

/// Build the part of the repository graph one TypeScript file states.
pub fn graph(source: Source, module: &str, specifiers: &Specifiers) -> Option<Stated> {
    let allocator = Allocator::default();
    let kind = SourceType::from_path(&source.relative)
        .expect("the TypeScript graph must receive a supported source suffix");
    // The parse borrows its text while the collector needs the source for positions. Each keeps
    // one copy so neither must borrow the other through the walk.
    let text = source.text.clone();
    let parsed = Parser::new(&allocator, &text, kind).parse();
    if parsed.panicked {
        return None;
    }
    let mut collector = Collector::new(source, module.to_string(), specifiers);
    collector.visit_program(&parsed.program);
    Some(collector.stated())
}
