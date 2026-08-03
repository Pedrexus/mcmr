use super::super::importer::ImportingModule;
use super::{Collector, ReferenceRequest, support::is_type_checking};
use crate::graph::construction::identity;
use crate::graph::contracts::{EdgeKind, Language, NodeKind, Reference};
use crate::walk::annotation_name;
use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::Ranged;

impl Collector {
    pub(super) fn statement(&mut self, statement: &Stmt) {
        if self.declaration_statement(statement) || self.binding_statement(statement) {
            return;
        }
        self.control_statement(statement);
    }

    fn declaration_statement(&mut self, statement: &Stmt) -> bool {
        match statement {
            Stmt::ClassDef(item) => self.class(statement, item),
            Stmt::FunctionDef(item) => self.callable(statement, item),
            _ => return false,
        }
        true
    }

    fn binding_statement(&mut self, statement: &Stmt) -> bool {
        match statement {
            Stmt::Assign(item) => {
                self.plain_assignment(statement, item);
            }
            Stmt::AnnAssign(item) => {
                self.annotated_assignment(statement, item);
            }
            Stmt::Import(item) => {
                self.plain_import(statement, item);
            }
            Stmt::ImportFrom(item) => {
                self.relative_import(statement, item);
            }
            _ => return false,
        }
        true
    }

    fn plain_assignment(&mut self, statement: &Stmt, item: &ruff_python_ast::StmtAssign) {
        for target in &item.targets {
            self.assignment(statement, target, None);
        }
        self.expression(&item.value);
    }

    fn annotated_assignment(&mut self, statement: &Stmt, item: &ruff_python_ast::StmtAnnAssign) {
        let annotation = annotation_name(&item.annotation);
        if let Expr::Name(name) = item.target.as_ref() {
            self.declare(name.id.as_str(), Some(annotation.clone()));
        }
        let owner = self.owners.last().unwrap().id.clone();
        self.annotation(&owner, &item.annotation);
        self.assignment(statement, &item.target, Some(annotation));
        if let Some(value) = &item.value {
            self.expression(value);
        }
    }

    fn plain_import(&mut self, statement: &Stmt, item: &ruff_python_ast::StmtImport) {
        for alias in &item.names {
            self.graph
                .aliases
                .insert(binding(alias), alias.name.to_string());
            self.import(
                alias.name.as_ref(),
                statement,
                Some(self.source.node_of("module", &alias.name)),
                item.names.len(),
            );
        }
    }

    fn relative_import(&mut self, statement: &Stmt, item: &ruff_python_ast::StmtImportFrom) {
        let importer = if self.is_package {
            ImportingModule::Package(&self.module)
        } else {
            ImportingModule::File(&self.module)
        };
        let target = importer.resolve(item);
        let module_node = item
            .module
            .as_ref()
            .map(|module| self.source.node_of("module", module));
        for alias in &item.names {
            self.relative_import_alias(
                statement,
                &target,
                alias,
                module_node.clone(),
                item.names.len(),
            );
        }
    }

    fn relative_import_alias(
        &mut self,
        statement: &Stmt,
        target: &str,
        alias: &ruff_python_ast::Alias,
        module_node: Option<crate::protocol::Node>,
        binding_count: usize,
    ) {
        let imported = format!("{target}.{}", alias.name);
        self.graph.aliases.insert(binding(alias), imported.clone());
        self.import(&imported, statement, module_node, binding_count);
        let owner = identity(Language::Python, NodeKind::Module, &self.module);
        self.reference(ReferenceRequest {
            source: &owner,
            expression: &imported,
            kind: EdgeKind::Access,
            offset: statement.range().start(),
        });
    }

    fn control_statement(&mut self, statement: &Stmt) {
        if let Stmt::If(item) = statement
            && is_type_checking(&item.test)
        {
            self.type_checking_imports(&item.body);
            for clause in &item.elif_else_clauses {
                self.body(&clause.body);
            }
            return;
        }
        for expression in crate::walk::expressions(statement) {
            self.expression(expression);
        }
        for block in crate::walk::blocks(statement) {
            self.body(block);
        }
    }

    fn type_checking_imports(&mut self, body: &[Stmt]) {
        for statement in body {
            match statement {
                Stmt::Import(item) => self.type_checking_plain_import(statement, item),
                Stmt::ImportFrom(item) => self.type_checking_relative_import(statement, item),
                _ => {}
            }
        }
    }

    fn type_checking_plain_import(
        &mut self,
        statement: &Stmt,
        item: &ruff_python_ast::StmtImport,
    ) {
        for alias in &item.names {
            let reference = self.import_reference(
                alias.name.as_ref(),
                statement,
                Some(self.source.node_of("module", &alias.name)),
                item.names.len(),
            );
            self.graph.export_references.push(reference);
        }
    }

    fn type_checking_relative_import(
        &mut self,
        statement: &Stmt,
        item: &ruff_python_ast::StmtImportFrom,
    ) {
        let importer = if self.is_package {
            ImportingModule::Package(&self.module)
        } else {
            ImportingModule::File(&self.module)
        };
        let target = importer.resolve(item);
        let module_node = item
            .module
            .as_ref()
            .map(|module| self.source.node_of("module", module));
        for alias in &item.names {
            let imported = format!("{target}.{}", alias.name);
            let reference =
                self.import_reference(&imported, statement, module_node.clone(), item.names.len());
            self.graph.export_references.push(reference);
        }
    }

    pub(super) fn import(
        &mut self,
        target: &str,
        statement: &Stmt,
        module_node: Option<crate::protocol::Node>,
        binding_count: usize,
    ) {
        let reference = self.import_reference(target, statement, module_node, binding_count);
        self.graph.references.push(reference);
    }

    fn import_reference(
        &self,
        target: &str,
        statement: &Stmt,
        module_node: Option<crate::protocol::Node>,
        binding_count: usize,
    ) -> Reference {
        Reference {
            language: Language::Python,
            source: identity(Language::Python, NodeKind::Module, &self.module),
            expression: target.to_string(),
            module: self.module.clone(),
            resolution: crate::graph::ReferenceResolution {
                owner: None,
                receiver_type: None,
                binding_count,
            },
            kind: EdgeKind::Import,
            location: crate::graph::ReferenceLocation {
                path: self.source.relative.clone(),
                line: self.source.line_of(statement.range().start()),
                module_node,
            },
        }
    }
}

fn binding(alias: &ruff_python_ast::Alias) -> String {
    alias
        .asname
        .as_ref()
        .map(ToString::to_string)
        .unwrap_or_else(|| alias.name.to_string())
}
