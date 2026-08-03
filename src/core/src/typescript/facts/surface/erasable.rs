use super::super::declarations::declared_class;
use crate::source::Source;
use crate::typescript::support::range;
use oxc_ast::ast::{ClassElement, Declaration, Function, Program, Statement};
use oxc_span::Span;
use serde_json::{Value, json};

/// Return each construct that type stripping cannot erase, which a runtime transform must handle.
///
/// A declaration reaches here whether it is exported or not, since `export enum Status` generates
/// exactly the object `enum Status` does and a reader stripping types is stopped by both.
pub(super) fn erasable(source: &Source, program: &Program) -> Vec<Value> {
    program
        .body
        .iter()
        .filter_map(|statement| {
            let item = surviving(statement)?;
            Some(json!({
                "kind": item.kind,
                "name": item.name,
                "line": source.line_of(range(item.span).start()),
            }))
        })
        .chain(parameter_properties(source, program))
        .collect()
}

/// Return what one statement declares that survives type stripping, looking through an export.
fn surviving(statement: &Statement) -> Option<Surviving> {
    let declaration = match statement {
        Statement::ExportNamedDeclaration(item) => item.declaration.as_ref()?,
        _ => statement.as_declaration()?,
    };
    surviving_declaration(declaration)
}

/// Return each constructor parameter that also declares a field, which stripping cannot erase.
fn parameter_properties(source: &Source, program: &Program) -> Vec<Value> {
    constructors(program)
        .flat_map(|function| function.params.items.iter())
        .filter(|parameter| parameter.accessibility.is_some() || parameter.readonly)
        .map(|parameter| parameter_property(source, parameter))
        .collect()
}

fn constructors<'a, 'ast>(program: &'a Program<'ast>) -> impl Iterator<Item = &'a Function<'ast>> {
    program
        .body
        .iter()
        .filter_map(declared_class)
        .flat_map(|class| class.body.body.iter())
        .filter_map(|member| match member {
            ClassElement::MethodDefinition(method) if method.kind.is_constructor() => {
                Some(method.value.as_ref())
            }
            _ => None,
        })
}

fn parameter_property(source: &Source, parameter: &oxc_ast::ast::FormalParameter<'_>) -> Value {
    let name = parameter
        .pattern
        .get_identifier_name()
        .map(|held| held.to_string())
        .expect("a TypeScript parameter property must state an identifier");
    json!({
        "kind": "parameter_property",
        "name": name,
        "line": source.line_of(range(parameter.span).start()),
    })
}

fn surviving_declaration(declaration: &Declaration<'_>) -> Option<Surviving> {
    match declaration {
        Declaration::TSEnumDeclaration(item) => Some(Surviving::enumeration(item)),
        Declaration::TSModuleDeclaration(item) => Some(Surviving::namespace(item)),
        Declaration::TSImportEqualsDeclaration(item) => Some(Surviving::import(item)),
        _ => None,
    }
}

struct Surviving {
    kind: String,
    name: String,
    span: Span,
}

impl Surviving {
    fn enumeration(item: &oxc_ast::ast::TSEnumDeclaration<'_>) -> Self {
        Self {
            kind: if item.r#const {
                "const_enum".to_string()
            } else {
                "enum".to_string()
            },
            name: item.id.name.to_string(),
            span: item.span,
        }
    }

    fn import(item: &oxc_ast::ast::TSImportEqualsDeclaration<'_>) -> Self {
        Self {
            kind: "import_equals".to_string(),
            name: item.id.name.to_string(),
            span: item.span,
        }
    }

    fn namespace(item: &oxc_ast::ast::TSModuleDeclaration<'_>) -> Self {
        Self {
            kind: "namespace".to_string(),
            name: item.id.name().to_string(),
            span: item.span,
        }
    }
}
