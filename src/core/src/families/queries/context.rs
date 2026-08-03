use super::super::imports::{direct_imports, resolve_imported};
use crate::walk::{annotation_name, qualified_name, walk};
use ruff_python_ast::{Expr, ExprCall, ModModule, Stmt};
use std::collections::{BTreeMap, BTreeSet};

/// SQLModel imports and declarations resolved for one module.
pub(super) struct SqlModelContext {
    imports: BTreeMap<String, String>,
    sessions: BTreeSet<String>,
    primary_keys: BTreeMap<String, BTreeSet<String>>,
}

impl SqlModelContext {
    pub(super) fn of(module: &ModModule) -> Self {
        let imports = direct_imports(module);
        let mut context = Self {
            imports,
            sessions: BTreeSet::new(),
            primary_keys: BTreeMap::new(),
        };
        for statement in walk(module) {
            context.observe(statement);
        }
        context
    }

    pub(super) fn is_primary_key_equality(&self, expression: &Expr, model: &str) -> bool {
        let Expr::Compare(comparison) = expression else {
            return false;
        };
        matches!(comparison.ops.as_ref(), [ruff_python_ast::CmpOp::Eq])
            && matches!(comparison.comparators.as_ref(), [_])
            && matches!(&*comparison.left, Expr::Attribute(attribute)
            if qualified_name(&attribute.value).rsplit('.').next() == Some(model)
                && self.primary_keys.get(model).is_some_and(|keys| {
                    keys.contains(attribute.attr.as_str())
                }))
    }

    pub(super) fn is_select(&self, call: &ExprCall) -> bool {
        self.resolve(&qualified_name(&call.func)) == "sqlmodel.select"
    }

    pub(super) fn is_session_receiver(&self, expression: &Expr) -> bool {
        self.sessions.contains(&qualified_name(expression))
    }

    fn add_function_sessions(&mut self, function: &ruff_python_ast::StmtFunctionDef) {
        let sessions = function
            .parameters
            .iter()
            .filter(|parameter| {
                parameter
                    .annotation()
                    .is_some_and(|annotation| self.is_session_type(annotation))
            })
            .map(|parameter| parameter.name().to_string())
            .collect::<Vec<_>>();
        self.sessions.extend(sessions);
    }

    fn add_table_keys(&mut self, class: &ruff_python_ast::StmtClassDef) {
        let keys = class
            .body
            .iter()
            .filter_map(|member| match member {
                Stmt::AnnAssign(field) if self.is_primary_key(field.value.as_deref()) => {
                    let name = qualified_name(&field.target);
                    (!name.is_empty()).then_some(name)
                }
                _ => None,
            })
            .collect();
        self.primary_keys.insert(class.name.to_string(), keys);
    }

    fn add_with_sessions(&mut self, statement: &ruff_python_ast::StmtWith) {
        for item in &statement.items {
            if !self.is_session_factory(&item.context_expr) {
                continue;
            }
            if let Some(target) = &item.optional_vars {
                let named = qualified_name(target);
                if !named.is_empty() {
                    self.sessions.insert(named);
                }
            }
        }
    }

    fn is_primary_key(&self, expression: Option<&Expr>) -> bool {
        matches!(expression, Some(Expr::Call(call))
        if self.resolve(&qualified_name(&call.func)) == "sqlmodel.Field"
            && call.arguments.keywords.iter().any(|keyword| {
                keyword.arg.as_ref().is_some_and(|name| name == "primary_key")
                    && matches!(&keyword.value, Expr::BooleanLiteral(value) if value.value)
            }))
    }

    fn is_session_factory(&self, expression: &Expr) -> bool {
        matches!(expression, Expr::Call(call) if self.is_session_type(&call.func))
    }

    fn is_session_type(&self, annotation: &Expr) -> bool {
        let resolved = self.resolve(&annotation_name(annotation));
        resolved.starts_with("sqlmodel.")
            && matches!(
                resolved.rsplit('.').next(),
                Some("Session" | "AsyncSession")
            )
    }

    fn is_sqlmodel_table(&self, class: &ruff_python_ast::StmtClassDef) -> bool {
        class.arguments.as_ref().is_some_and(|arguments| {
            arguments.args.iter().any(|base| {
                let resolved = self.resolve(&qualified_name(base));
                resolved == "sqlmodel.SQLModel"
            }) && arguments.keywords.iter().any(|keyword| {
                keyword.arg.as_ref().is_some_and(|name| name == "table")
                    && matches!(&keyword.value, Expr::BooleanLiteral(value) if value.value)
            })
        })
    }

    fn observe(&mut self, statement: &Stmt) {
        match statement {
            Stmt::FunctionDef(function) => self.add_function_sessions(function),
            Stmt::AnnAssign(assignment) if self.is_session_type(&assignment.annotation) => {
                let named = qualified_name(&assignment.target);
                if !named.is_empty() {
                    self.sessions.insert(named);
                }
            }
            Stmt::Assign(assignment) if self.is_session_factory(&assignment.value) => {
                self.sessions.extend(
                    assignment
                        .targets
                        .iter()
                        .map(qualified_name)
                        .filter(|name| !name.is_empty()),
                );
            }
            Stmt::With(statement) => self.add_with_sessions(statement),
            Stmt::ClassDef(class) if self.is_sqlmodel_table(class) => self.add_table_keys(class),
            _ => {}
        }
    }

    fn resolve(&self, written: &str) -> String {
        resolve_imported(&self.imports, written)
    }
}
