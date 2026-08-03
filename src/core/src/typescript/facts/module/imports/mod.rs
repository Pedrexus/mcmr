use crate::protocol::JsonObject;
use crate::source::Source;
use crate::typescript::support::base;
use crate::typescript::support::range;
use names::ImportedNames;
use oxc_ast::ast::{ImportDeclaration, ImportDeclarationSpecifier, Program, Statement};
use serde_json::{Value, json};

mod names;

pub(in crate::typescript::facts) fn import_facts(
    source: &Source,
    program: &Program,
) -> Vec<Value> {
    program
        .body
        .iter()
        .filter_map(|statement| match statement {
            Statement::ImportDeclaration(item) => Some(import_declaration(source, item)),
            _ => None,
        })
        .flatten()
        .collect()
}

fn import_declaration(source: &Source, item: &ImportDeclaration<'_>) -> Vec<Value> {
    item.specifiers
        .iter()
        .flatten()
        .map(|specifier| ImportedBinding::new(item, specifier).fact(source))
        .collect()
}

struct ImportedBinding {
    bound: String,
    imported_name: String,
    is_type_only: bool,
    module: String,
    span: oxc_span::Span,
}

impl ImportedBinding {
    fn new(
        declaration: &ImportDeclaration<'_>,
        specifier: &ImportDeclarationSpecifier<'_>,
    ) -> Self {
        let names = ImportedNames::new(specifier);
        Self {
            bound: names.bound,
            imported_name: names.imported,
            is_type_only: is_type_only(declaration, specifier),
            module: declaration.source.value.to_string(),
            span: declaration.span,
        }
    }

    fn fact(self, source: &Source) -> Value {
        let references = self.references(source);
        let key = format!("import:{}:{}", source.relative, self.bound);
        JsonObject::new(base(source, &key)).merged(self.value(source, references))
    }

    fn references(&self, source: &Source) -> usize {
        source
            .text
            .matches(&self.bound)
            .count()
            .checked_sub(1)
            .expect("an imported binding must occur in its own declaration")
    }

    fn value(self, source: &Source, references: usize) -> Value {
        let relative = self.module.starts_with('.');
        json!({
            "name": self.bound,
            "module": self.module,
            "imported_name": self.imported_name,
            "importer_module": source.relative.clone(),
            "declaration": source.node("import", range(self.span)),
            "reference_count": references,
            "has_qualifying_use": references > 0,
            "is_relative": relative,
            "is_project_owned": relative,
            "is_external": !relative,
            "is_type_only": self.is_type_only,
        })
    }
}

fn is_type_only(
    declaration: &ImportDeclaration<'_>,
    specifier: &ImportDeclarationSpecifier<'_>,
) -> bool {
    declaration.import_kind.is_type()
        || matches!(specifier, ImportDeclarationSpecifier::ImportSpecifier(named) if named.import_kind.is_type())
}
