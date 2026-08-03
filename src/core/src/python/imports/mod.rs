use crate::discovery::Packages;
use crate::protocol::JsonObject;
use crate::source::Source;
use crate::walk::{annotation_name, blocks, qualified_name};
use ruff_python_ast::{Alias, Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

use super::fact::base;
use super::reference_index::ReferenceIndex;

mod exports;
mod guard;
mod import_context;
mod import_site;

pub(super) use exports::declares_all;
pub(crate) use exports::{exported_names, exported_nodes};
use guard::ImportGuard;
use import_context::ImportContext;
use import_site::ImportSite;

struct ImportCollector<'a> {
    source: &'a Source,
    context: &'a ImportContext,
    facts: Vec<Value>,
}

pub(super) fn import_facts(
    source: &Source,
    packages: &Packages,
    module: &ModModule,
) -> Vec<Value> {
    let context = ImportContext {
        importer: packages.module_name(&source.relative),
        references: ReferenceIndex::of(module),
        exported: exported_names(module),
    };
    let mut collector = ImportCollector {
        source,
        context: &context,
        facts: Vec::new(),
    };
    collector.collect_imports(&module.body, ImportGuard::Unguarded, false);
    collector.facts
}

impl ImportCollector<'_> {
    /// Push one fact per name the imports in one block bind, carrying its enclosing guard.
    fn collect_imports(&mut self, body: &[Stmt], guard: ImportGuard, is_type_only: bool) {
        for statement in body {
            self.collect_import_statement(statement, guard, is_type_only);
        }
    }

    fn collect_import_statement(
        &mut self,
        statement: &Stmt,
        guard: ImportGuard,
        is_type_only: bool,
    ) {
        match statement {
            Stmt::Import(item) => self.collect_direct_import(statement, item, guard, is_type_only),
            Stmt::ImportFrom(item) => {
                self.collect_from_import(statement, item, guard, is_type_only);
            }
            Stmt::Try(item) => self.collect_try_imports(item, guard, is_type_only),
            Stmt::If(item) => {
                let guarded = is_type_only || qualified_name(&item.test) == "TYPE_CHECKING";
                self.collect_imports(&item.body, guard, guarded);
                for clause in &item.elif_else_clauses {
                    self.collect_imports(&clause.body, guard, is_type_only);
                }
            }
            _ => {
                for block in blocks(statement) {
                    self.collect_imports(block, guard, is_type_only);
                }
            }
        }
    }

    fn collect_direct_import(
        &mut self,
        statement: &Stmt,
        item: &ruff_python_ast::StmtImport,
        guard: ImportGuard,
        is_type_only: bool,
    ) {
        self.facts.extend(item.names.iter().map(|alias| {
            import_fact(
                self.source,
                self.context,
                alias,
                ImportSite {
                    statement,
                    module: alias.name.as_str(),
                    level: 0,
                    binding_count: item.names.len(),
                    is_guarded: guard.is_guarded(),
                    is_type_only,
                },
            )
        }));
    }

    fn collect_from_import(
        &mut self,
        statement: &Stmt,
        item: &ruff_python_ast::StmtImportFrom,
        guard: ImportGuard,
        is_type_only: bool,
    ) {
        let module = item
            .module
            .as_ref()
            .map(ruff_python_ast::Identifier::as_str)
            .unwrap_or_default();
        self.facts.extend(item.names.iter().map(|alias| {
            import_fact(
                self.source,
                self.context,
                alias,
                ImportSite {
                    statement,
                    module,
                    level: item.level,
                    binding_count: item.names.len(),
                    is_guarded: guard.is_guarded(),
                    is_type_only,
                },
            )
        }));
    }

    fn collect_try_imports(
        &mut self,
        item: &ruff_python_ast::StmtTry,
        guard: ImportGuard,
        is_type_only: bool,
    ) {
        let protected = if guards_import_failure(item) {
            ImportGuard::Guarded
        } else {
            guard
        };
        self.collect_imports(&item.body, protected, is_type_only);
        for handler in &item.handlers {
            let ruff_python_ast::ExceptHandler::ExceptHandler(held) = handler;
            self.collect_imports(&held.body, guard, is_type_only);
        }
        self.collect_imports(&item.orelse, guard, is_type_only);
        self.collect_imports(&item.finalbody, guard, is_type_only);
    }
}

/// Whether one `try` states what to do when an import inside it fails.
fn guards_import_failure(item: &ruff_python_ast::StmtTry) -> bool {
    item.handlers.iter().any(|handler| {
        let ruff_python_ast::ExceptHandler::ExceptHandler(held) = handler;
        held.type_.as_deref().is_none_or(catches_import_failure)
    })
}

/// Whether one `except` clause names the failure a missing module raises.
fn catches_import_failure(caught: &Expr) -> bool {
    match caught {
        Expr::Tuple(item) => item.elts.iter().any(catches_import_failure),
        _ => matches!(
            annotation_name(caught).as_str(),
            "ImportError" | "ModuleNotFoundError"
        ),
    }
}

fn import_fact(
    source: &Source,
    context: &ImportContext,
    alias: &Alias,
    site: ImportSite<'_>,
) -> Value {
    let imported = alias.name.to_string();
    let bound = alias
        .asname
        .as_ref()
        .map(ToString::to_string)
        .unwrap_or_else(|| imported.split('.').next().unwrap_or(&imported).to_string());
    let references = context.references.reads(&bound);
    let root = site.module.split('.').next().unwrap_or(site.module);
    let project = context
        .importer
        .split('.')
        .next()
        .unwrap_or(&context.importer);
    let is_private_member = imported.starts_with('_') && !imported.starts_with("__");
    let is_private_uppercase_constant = is_private_member
        && imported
            .strip_prefix('_')
            .is_some_and(|name| name.chars().all(|character| !character.is_lowercase()));
    let key = format!("import:{}:{}", source.relative, bound);
    JsonObject::new(base(source, &key, site.statement.range())).merged(json!({
        "name": bound,
        "module": site.module,
        "imported_name": imported,
        "importer_module": context.importer,
        "declaration": source.node_of("import", site.statement),
        "binding": source.node_of("sequence-item", alias),
        "module_node": match site.statement {
            Stmt::Import(_) => Some(source.node_of("module", &alias.name)),
            Stmt::ImportFrom(item) => item
                .module
                .as_ref()
                .map(|module| source.node_of("module", module)),
            _ => None,
        },
        "references": context.references.locations(&bound).iter().map(|range| {
            source.node("reference", *range)
        }).collect::<Vec<_>>(),
        "relative_level": site.level,
        "reference_count": references,
        "has_qualifying_use": references > 0,
        "has_documented_side_effect": site.is_guarded,
        "is_sole_binding": site.binding_count == 1,
        "is_relative": site.level > 0,
        "is_type_only": site.is_type_only,
        "is_project_owned": site.level > 0 || root == project,
        "is_external": site.level == 0 && root != project,
        "is_wildcard": imported == "*",
        "is_reexported": context.exported.contains(&bound)
            || alias.asname.as_ref().map(ToString::to_string).as_deref()
                == Some(imported.as_str()),
        "is_private_member": is_private_member,
        "is_private_uppercase_constant": is_private_uppercase_constant,
        "has_private_module_component": site.module.split('.').any(|part| {
            part.starts_with('_') && !part.starts_with("__")
        }),
    }))
}
