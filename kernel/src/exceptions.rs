use crate::discovery::{Document, Packages};
use crate::graph::absolute_module;
use crate::walk::{docstring, qualified_name};
use rayon::prelude::*;
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_python_parser::parse_module;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// Every project exception class, with the ordinary modules that import it by name.
///
/// Where an exception belongs is a question about the whole repository rather than about the file
/// that raises it, so no per-file pass can answer it. This one reads every module once, keeps what
/// each declares and what each imports, and joins the two. A rule asking which exceptions are
/// shared contracts then reads consumers that were resolved rather than assumed.
pub fn facts(documents: &[Document], packages: &Packages) -> Vec<Value> {
    let stated: Vec<Stated> = documents
        .par_iter()
        .filter(|document| document.relative.ends_with(".py"))
        .filter_map(|document| Stated::of(document, packages))
        .collect();
    let exceptions = errors(&stated);
    let importers = importers(&stated, &exceptions);
    stated
        .iter()
        .filter_map(|module| module.fact(&exceptions, &importers))
        .collect()
}

/// What one module states about the exceptions it declares and the names it imports.
struct Stated {
    module: String,
    path: String,
    is_package: bool,
    is_reexport_only: bool,
    declared: Vec<Declared>,
    imported: Vec<(String, String)>,
}

/// One top-level class and the bases it names, before anything decides what those bases are.
struct Declared {
    name: String,
    bases: Vec<String>,
}

impl Stated {
    fn of(document: &Document, packages: &Packages) -> Option<Self> {
        let parsed = parse_module(&document.source).ok()?;
        let module = parsed.syntax();
        let name = packages.module_name(&document.relative);
        let is_package = document.relative.ends_with("/__init__.py");
        Some(Self {
            declared: declarations(module),
            imported: imports(module, &name, is_package),
            is_reexport_only: is_reexport_only(module),
            module: name,
            path: document.relative.clone(),
            is_package,
        })
    }

    /// State one module's exception classes, or nothing when it declares none.
    fn fact(
        &self,
        exceptions: &BTreeSet<&str>,
        importers: &BTreeMap<(&str, &str), BTreeSet<&str>>,
    ) -> Option<Value> {
        let declared: Vec<Value> = self
            .declared
            .iter()
            .filter(|class| exceptions.contains(class.name.as_str()))
            .map(|class| {
                json!({
                    "name": class.name,
                    "defining_module": self.module,
                    "importing_modules": importers
                        .get(&(self.module.as_str(), class.name.as_str()))
                        .map(|found| found.iter().copied().collect::<Vec<_>>())
                        .unwrap_or_default(),
                })
            })
            .collect();
        (!declared.is_empty()).then(|| {
            json!({
                "key": format!("exceptions:{}", self.module),
                "span": {"path": self.path},
                "language": "python",
                "exceptions": declared,
            })
        })
    }
}

/// Return every top-level class one module declares, with the bases each names.
fn declarations(module: &ModModule) -> Vec<Declared> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(item) => Some(Declared {
                name: item.name.to_string(),
                bases: item
                    .arguments
                    .iter()
                    .flat_map(|arguments| arguments.args.iter())
                    .map(|base| last_segment(&qualified_name(base)).to_string())
                    .collect(),
            }),
            _ => None,
        })
        .collect()
}

/// Return every explicit `from` import one module states, as the module and name it reaches.
///
/// A star import names nothing, so it proves no module depends on any particular class and is left
/// out. Everything else arrives resolved against the importing module's own package, which is what
/// makes a relative import comparable to the definition it reaches.
fn imports(module: &ModModule, name: &str, is_package: bool) -> Vec<(String, String)> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ImportFrom(item) => Some(item),
            _ => None,
        })
        .flat_map(|item| {
            let target = absolute_module(name, is_package, item);
            item.names
                .iter()
                .filter(|alias| alias.name.as_str() != "*")
                .map(move |alias| (target.clone(), alias.name.to_string()))
        })
        .collect()
}

/// Whether one module hands names on rather than declaring anything of its own.
///
/// A module holding nothing but imports is a seam, so importing through it does not prove that a
/// second place depends on the name. Its own consumers do, and they are counted where they are.
fn is_reexport_only(module: &ModModule) -> bool {
    let body = match module.body.split_first() {
        Some((first, rest)) if docstring(std::slice::from_ref(first)).is_some() => rest,
        _ => module.body.as_slice(),
    };
    body.iter().all(|statement| match statement {
        Stmt::Import(_) | Stmt::ImportFrom(_) => true,
        Stmt::Assign(item) => item
            .targets
            .iter()
            .all(|target| matches!(target, Expr::Name(name) if name.id.as_str() == "__all__")),
        _ => false,
    })
}

/// Return the names of every class this repository derives from an exception.
///
/// The seed is a base named as an error, which is the convention every language in this family
/// keeps, and the closure is a class deriving from one already known. Both compare bare names,
/// since a base is written as whatever the importing module bound it to and only the repository as
/// a whole knows what that reaches.
fn errors(stated: &[Stated]) -> BTreeSet<&str> {
    let mut found: BTreeSet<&str> = stated
        .iter()
        .flat_map(|module| module.declared.iter())
        .filter(|class| class.bases.iter().any(|base| is_error_named(base)))
        .map(|class| class.name.as_str())
        .collect();
    loop {
        let grown: BTreeSet<&str> = stated
            .iter()
            .flat_map(|module| module.declared.iter())
            .filter(|class| class.bases.iter().any(|base| found.contains(base.as_str())))
            .map(|class| class.name.as_str())
            .collect();
        let before = found.len();
        found.extend(grown);
        if found.len() == before {
            return found;
        }
    }
}

fn is_error_named(base: &str) -> bool {
    base.contains("Error") || base.contains("Exception")
}

fn last_segment(name: &str) -> &str {
    name.rsplit('.').next().unwrap_or(name)
}

/// Return which ordinary modules import each declared exception, keyed by definition.
///
/// A package initializer and a module of nothing but imports are both re-export seams rather than
/// consumers, and the module holding the definition is not a consumer of itself, so none of the
/// three counts toward the reuse a placement rule measures.
fn importers<'stated>(
    stated: &'stated [Stated],
    exceptions: &BTreeSet<&str>,
) -> BTreeMap<(&'stated str, &'stated str), BTreeSet<&'stated str>> {
    let mut found: BTreeMap<(&str, &str), BTreeSet<&str>> = BTreeMap::new();
    for module in stated {
        if module.is_package || module.is_reexport_only {
            continue;
        }
        for (target, name) in &module.imported {
            if target == &module.module || !exceptions.contains(name.as_str()) {
                continue;
            }
            found
                .entry((target.as_str(), name.as_str()))
                .or_default()
                .insert(module.module.as_str());
        }
    }
    found
}

#[cfg(test)]
mod tests {
    use super::*;

    fn facts_of(sources: &[(&str, &str)]) -> Vec<Value> {
        let documents: Vec<Document> = sources
            .iter()
            .map(|(relative, source)| Document {
                relative: (*relative).to_string(),
                source: (*source).to_string(),
            })
            .collect();
        let packages = Packages::of(&documents);
        facts(&documents, &packages)
    }

    fn stated<'a>(facts: &'a [Value], name: &str) -> &'a Value {
        facts
            .iter()
            .flat_map(|fact| fact["exceptions"].as_array().expect("a list").iter())
            .find(|exception| exception["name"] == name)
            .expect("the exception is declared")
    }

    #[test]
    fn an_exception_carries_the_modules_that_import_it_by_name() {
        let facts = facts_of(&[
            ("shop/__init__.py", ""),
            (
                "shop/service.py",
                "class OrderConflictError(Exception):\n    pass\n",
            ),
            (
                "shop/api.py",
                "from shop.service import OrderConflictError\n\n\ndef place() -> None:\n    raise OrderConflictError\n",
            ),
            (
                "shop/jobs.py",
                "from .service import OrderConflictError\n\n\ndef sweep() -> None:\n    raise OrderConflictError\n",
            ),
        ]);

        assert_eq!(
            stated(&facts, "OrderConflictError")["importing_modules"],
            json!(["shop.api", "shop.jobs"])
        );
        assert_eq!(
            stated(&facts, "OrderConflictError")["defining_module"],
            "shop.service"
        );
    }

    #[test]
    fn a_package_initializer_and_a_reexport_module_are_not_consumers() {
        let facts = facts_of(&[
            ("shop/__init__.py", "from .service import OrderError\n"),
            (
                "shop/service.py",
                "class OrderError(Exception):\n    pass\n",
            ),
            (
                "shop/seam.py",
                "from .service import OrderError\n\n__all__ = [\"OrderError\"]\n",
            ),
        ]);

        assert_eq!(
            stated(&facts, "OrderError")["importing_modules"],
            json!([] as [&str; 0])
        );
    }

    #[test]
    fn a_class_deriving_from_a_project_exception_is_an_exception_too() {
        let facts = facts_of(&[
            ("shop/__init__.py", ""),
            (
                "shop/service.py",
                "class OrderError(Exception):\n    pass\n\n\nclass LineOrderError(OrderError):\n    pass\n\n\nclass Report:\n    pass\n",
            ),
        ]);

        assert_eq!(facts.len(), 1);
        assert_eq!(
            facts[0]["exceptions"]
                .as_array()
                .expect("a list")
                .iter()
                .map(|item| item["name"].as_str().unwrap_or_default())
                .collect::<Vec<_>>(),
            ["OrderError", "LineOrderError"]
        );
    }

    #[test]
    fn a_star_import_and_a_self_import_prove_no_consumer() {
        let facts = facts_of(&[
            ("shop/__init__.py", ""),
            (
                "shop/service.py",
                "from .service import OrderError\n\n\nclass OrderError(Exception):\n    pass\n",
            ),
            (
                "shop/api.py",
                "from shop.service import *\n\n\ndef place() -> None:\n    raise OrderError\n",
            ),
        ]);

        assert_eq!(
            stated(&facts, "OrderError")["importing_modules"],
            json!([] as [&str; 0])
        );
    }

    #[test]
    fn a_repository_declaring_no_exception_states_nothing() {
        assert!(facts_of(&[("alone.py", "class Report:\n    pass\n")]).is_empty());
    }
}
