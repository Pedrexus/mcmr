use super::identity::Identity;
use super::location::ModuleLocation;
use super::named::NamedDefinition;
use crate::discovery::{Document, Packages};
use crate::graph::{ImportingModule, absolute_module};
use crate::organization::paths::tail;
use crate::protocol::Span;
use crate::source::{Source, is_test_path};
use crate::walk::qualified_name;
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_python_parser::parse_module;
use ruff_text_size::Ranged;
use std::collections::BTreeMap;

pub(crate) struct Module {
    pub(crate) location: ModuleLocation,
    pub(crate) top_level_class_count: usize,
    pub(crate) enums: Vec<String>,
    pub(crate) typings: Vec<NamedDefinition>,
    pub(crate) imports: BTreeMap<Identity, Span>,
}

impl Module {
    pub(crate) fn of(document: &Document, packages: &Packages) -> Option<Self> {
        let source = Source::new(document);
        let parsed = parse_module(&source.text).ok()?;
        let syntax = parsed.syntax();
        let name = packages.module_name(&document.relative);
        let importer = ImportingModule::for_document(&name, document);
        Some(Self {
            location: ModuleLocation {
                name: name.clone(),
                path: document.relative.clone(),
                is_package: document.relative.ends_with("/__init__.py"),
                is_test: is_test_path(&document.relative)
                    || document
                        .relative
                        .split('/')
                        .any(|component| component == "tests"),
            },
            top_level_class_count: syntax
                .body
                .iter()
                .filter(|statement| matches!(statement, Stmt::ClassDef(_)))
                .count(),
            enums: enum_names(syntax),
            typings: typing_names(syntax, &source),
            imports: imports(syntax, &source, importer),
        })
    }
}

fn enum_names(module: &ModModule) -> Vec<String> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(class) => {
                let bases = class
                    .arguments
                    .iter()
                    .flat_map(|arguments| arguments.args.iter())
                    .map(qualified_name)
                    .collect::<Vec<_>>();
                crate::families::is_enum(&bases).then(|| class.name.to_string())
            }
            _ => None,
        })
        .collect()
}

fn typing_names(module: &ModModule, source: &Source) -> Vec<NamedDefinition> {
    module
        .body
        .iter()
        .filter_map(|statement| {
            let name = match statement {
                Stmt::TypeAlias(alias) => match alias.name.as_ref() {
                    Expr::Name(name) => Some(name.id.to_string()),
                    _ => None,
                },
                Stmt::AnnAssign(assignment)
                    if tail(&qualified_name(&assignment.annotation)) == "TypeAlias" =>
                {
                    named(&assignment.target)
                }
                Stmt::Assign(assignment) if typing_factory(&assignment.value) => assignment
                    .targets
                    .as_slice()
                    .first()
                    .filter(|_| assignment.targets.len() == 1)
                    .and_then(named),
                Stmt::ClassDef(class)
                    if class
                        .arguments
                        .iter()
                        .flat_map(|arguments| arguments.args.iter())
                        .map(qualified_name)
                        .any(|base| matches!(tail(&base), "Protocol" | "TypedDict")) =>
                {
                    Some(class.name.to_string())
                }
                _ => None,
            }?;
            Some(NamedDefinition {
                name,
                span: source.span(statement.range()),
            })
        })
        .collect()
}

fn typing_factory(expression: &Expr) -> bool {
    matches!(expression, Expr::Call(call)
    if matches!(
        tail(&qualified_name(&call.func)),
        "NewType" | "NamedTuple" | "TypedDict" | "TypeVar" | "ParamSpec" | "TypeVarTuple"
    ))
}

fn named(expression: &Expr) -> Option<String> {
    match expression {
        Expr::Name(name) => Some(name.id.to_string()),
        _ => None,
    }
}

fn imports(
    module: &ModModule,
    source: &Source,
    importer: ImportingModule<'_>,
) -> BTreeMap<Identity, Span> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ImportFrom(imported) => Some(imported),
            _ => None,
        })
        .flat_map(|imported| {
            let origin = absolute_module(importer, imported);
            imported
                .names
                .iter()
                .filter(|alias| alias.name.as_str() != "*")
                .map(move |alias| {
                    (
                        (origin.clone(), alias.name.to_string()),
                        source.span(alias.range()),
                    )
                })
        })
        .collect()
}
