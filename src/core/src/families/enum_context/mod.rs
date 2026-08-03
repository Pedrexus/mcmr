use super::collections::{comprehension_clauses, owned, stated};
use super::enum_facts::enum_kind;
use crate::walk::{annotation_name, children, qualified_name, walk};
use ruff_python_ast::{Expr, ModModule, Parameters, Stmt};
use std::collections::BTreeMap;

mod bindings;
mod enums;

pub(super) use bindings::Bindings;
pub(super) use enums::Enums;

/// The enumerations one file declares, keyed by name, with the standard bases each derives.
///
/// A base is recorded under the name the standard `enum` module gives it, so a module writing
/// `from enum import StrEnum as Base` reaches the same answer as one writing it out. A class
/// stating its own `__str__` or `__int__` is left out entirely, because the conversion a rule
/// would recommend for it is no longer the one the standard base performs.
impl Enums {
    pub(super) fn of(module: &ModModule) -> Self {
        let aliases = enum_aliases(module);
        let declared = walk(module)
            .into_iter()
            .filter_map(|statement| match statement {
                Stmt::ClassDef(item) => Some(item),
                _ => None,
            })
            .filter(|item| !states_own_conversion(item))
            .filter_map(|item| {
                let bases: Vec<String> = item
                    .arguments
                    .iter()
                    .flat_map(|arguments| arguments.args.iter())
                    .map(|base| {
                        let written = qualified_name(base);
                        let tail = written.rsplit('.').next().unwrap_or(&written).to_string();
                        aliases.get(&tail).cloned().unwrap_or(tail)
                    })
                    .collect();
                enum_kind(&bases).map(|_| (item.name.to_string(), bases))
            })
            .collect();
        Self { declared }
    }

    pub(super) fn holds(&self, name: &str) -> bool {
        self.declared.contains_key(name)
    }

    pub(super) fn bases(&self, name: &str) -> Vec<String> {
        self.declared.get(name).cloned().unwrap_or_default()
    }
}

/// Return what each name a module imports from `enum` is called in the standard module.
fn enum_aliases(module: &ModModule) -> BTreeMap<String, String> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ImportFrom(item)
                if item.level == 0
                    && item
                        .module
                        .as_ref()
                        .is_some_and(|name| name.as_str() == "enum") =>
            {
                Some(item)
            }
            _ => None,
        })
        .flat_map(|item| item.names.iter())
        .filter_map(|alias| {
            alias
                .asname
                .as_ref()
                .map(|bound| (bound.to_string(), alias.name.to_string()))
        })
        .collect()
}

/// Whether one class replaces the conversion its standard enum base would otherwise perform.
fn states_own_conversion(item: &ruff_python_ast::StmtClassDef) -> bool {
    item.body.iter().any(|member| {
        matches!(member, Stmt::FunctionDef(method)
            if matches!(method.name.as_str(), "__str__" | "__int__"))
    })
}

/// The names one scope binds exactly once to a value whose enumeration this file states.
///
/// Binding a name twice is what makes it ambiguous, so every binding is counted and only the names
/// bound once survive. That is the whole of the proof, and a name reached any other way stays
/// unknown rather than being guessed at from its spelling.
impl Bindings {
    pub(super) fn of(parameters: Option<&Parameters>, body: &[Stmt], enums: &Enums) -> Self {
        let mut counted: BTreeMap<String, usize> = BTreeMap::new();
        let mut proven: BTreeMap<String, String> = BTreeMap::new();
        let annotated = parameters
            .into_iter()
            .flat_map(|held| held.iter())
            .map(|item| {
                let named = item
                    .annotation()
                    .map(annotation_name)
                    .filter(|held| enums.holds(held));
                (item.name().to_string(), named)
            });
        for (name, held) in annotated.chain(scope_bindings(body, enums)) {
            *counted.entry(name.clone()).or_default() += 1;
            if let Some(class) = held {
                proven.insert(name, class);
            }
        }
        Self {
            names: proven
                .into_iter()
                .filter(|(name, _)| counted.get(name) == Some(&1))
                .collect(),
        }
    }

    /// Return the enumeration one receiver expression is proven to be a member of.
    pub(super) fn enum_of<'enums>(
        &self,
        receiver: &Expr,
        enums: &'enums Enums,
    ) -> Option<&'enums str> {
        let named = match receiver {
            Expr::Name(item) => self.names.get(item.id.as_str()).cloned(),
            Expr::Attribute(item) => Some(qualified_name(&item.value)),
            Expr::Call(item) => Some(qualified_name(&item.func)),
            Expr::Subscript(item) => Some(qualified_name(&item.value)),
            _ => None,
        }?;
        enums
            .declared
            .get_key_value(named.as_str())
            .map(|(held, _)| held.as_str())
    }
}

/// Return every name one scope binds, with the enumeration the binding proves where it proves one.
fn scope_bindings(body: &[Stmt], enums: &Enums) -> Vec<(String, Option<String>)> {
    let mut found = Vec::new();
    for statement in owned(body) {
        match statement {
            Stmt::Assign(item) => found.extend(
                item.targets
                    .iter()
                    .map(|target| (bound_name(target), member_of(&item.value, enums))),
            ),
            Stmt::AnnAssign(item) => found.push((
                bound_name(&item.target),
                Some(annotation_name(&item.annotation)).filter(|held| enums.holds(held)),
            )),
            Stmt::For(item) => found.push((bound_name(&item.target), iterated(&item.iter, enums))),
            Stmt::AugAssign(item) => found.push((bound_name(&item.target), None)),
            Stmt::With(item) => found.extend(
                item.items
                    .iter()
                    .filter_map(|entry| entry.optional_vars.as_deref())
                    .map(|target| (bound_name(target), None)),
            ),
            _ => {}
        }
        for expression in stated(statement) {
            comprehension_bindings(expression, enums, &mut found);
        }
    }
    found.retain(|(name, _)| !name.is_empty());
    found
}

fn comprehension_bindings(
    expression: &Expr,
    enums: &Enums,
    found: &mut Vec<(String, Option<String>)>,
) {
    for generator in comprehension_clauses(expression) {
        found.push((
            bound_name(&generator.target),
            iterated(&generator.iter, enums),
        ));
    }
    for child in children(expression) {
        comprehension_bindings(child, enums, found);
    }
}

pub(super) fn bound_name(target: &Expr) -> String {
    match target {
        Expr::Name(item) => item.id.to_string(),
        _ => String::new(),
    }
}

/// Return the enumeration one value expression proves its name holds a member of.
fn member_of(value: &Expr, enums: &Enums) -> Option<String> {
    let named = match value {
        Expr::Attribute(item) => qualified_name(&item.value),
        Expr::Call(item) => qualified_name(&item.func),
        Expr::Subscript(item) => qualified_name(&item.value),
        _ => return None,
    };
    enums.holds(&named).then_some(named)
}

/// Return the enumeration one loop proves its target holds a member of.
fn iterated(iterable: &Expr, enums: &Enums) -> Option<String> {
    let named = qualified_name(iterable);
    enums.holds(&named).then_some(named)
}
