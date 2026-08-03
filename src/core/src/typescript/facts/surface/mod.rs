use crate::protocol::JsonObject;
use crate::source::Source;
use crate::typescript::support::base;
use erasable::erasable;
use escapes::escape_hatches;
use oxc_ast::ast::{Program, Statement};
use serde_json::{Value, json};

mod erasable;
mod escapes;

/// What one module publishes, how far its callers reach for it, and where it steps around types.
pub(super) fn surface(source: &Source, program: &Program) -> Value {
    let mut exports = ModuleSurface::default();
    exports.read(program);
    exports.fact(source, program)
}

#[derive(Default)]
struct ModuleSurface {
    deepest: String,
    export_count: usize,
    named_reexport_count: usize,
    star_reexports: Vec<String>,
}

impl ModuleSurface {
    fn export_all(&mut self, item: &oxc_ast::ast::ExportAllDeclaration<'_>) {
        self.star_reexports.push(item.source.value.to_string());
        self.deepest = climbed(std::mem::take(&mut self.deepest), &item.source.value);
    }

    fn export_named(&mut self, item: &oxc_ast::ast::ExportNamedDeclaration<'_>) {
        self.export_count += 1;
        if let Some(from) = &item.source {
            self.named_reexport_count += item.specifiers.len();
            self.deepest = climbed(std::mem::take(&mut self.deepest), &from.value);
        }
    }

    fn fact(self, source: &Source, program: &Program) -> Value {
        JsonObject::new(base(source, &format!("surface:{}", source.relative))).merged(json!({
            "star_reexports": self.star_reexports,
            "named_reexport_count": self.named_reexport_count,
            "export_count": self.export_count,
            "is_index_module": source.relative.ends_with("/index.ts")
                || source.relative == "index.ts",
            "deepest_relative_import": relative_depth(&self.deepest),
            "deepest_relative_specifier": self.deepest,
            "erasable_violations": erasable(source, program),
            "escape_hatches": escape_hatches(source, program),
            "physical_line_count": source.text.lines().count(),
        }))
    }

    fn import(&mut self, item: &oxc_ast::ast::ImportDeclaration<'_>) {
        self.deepest = climbed(std::mem::take(&mut self.deepest), &item.source.value);
    }

    fn read(&mut self, program: &Program) {
        for statement in &program.body {
            match statement {
                Statement::ExportAllDeclaration(item) => self.export_all(item),
                Statement::ExportNamedDeclaration(item) => self.export_named(item),
                Statement::ExportDefaultDeclaration(_) => self.export_count += 1,
                Statement::ImportDeclaration(item) => self.import(item),
                _ => {}
            }
        }
    }
}

/// Return whichever of two specifiers climbs further out of the directory that wrote it.
fn climbed(held: String, candidate: &str) -> String {
    match relative_depth(candidate) > relative_depth(&held) {
        true => candidate.to_string(),
        false => held,
    }
}

/// Return how many directories one relative import climbs before it finds its target.
fn relative_depth(specifier: &str) -> usize {
    specifier.matches("../").count()
}
