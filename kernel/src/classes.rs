use crate::discovery::{Document, Packages};
use crate::graph::absolute_module;
use crate::source::Source;
use crate::walk::{blocks, docstring, expressions, qualified_name, walk};
use rayon::prelude::*;
use ruff_python_ast::{Expr, ModModule, Stmt, StmtClassDef};
use ruff_python_parser::parse_module;
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// Answer over the whole repository what one file cannot say about the classes it declares.
///
/// Who subclasses a class, who builds one, who imports it, and what its bases already provide are
/// all questions about every module at once, so a per-file pass answers them with a default and a
/// rule reading that default answers the same thing forever. This reads every module once, joins
/// what each declares to what each reaches, and writes the answers back onto the facts the file
/// pass already produced.
pub fn enrich(
    facts: &mut BTreeMap<String, Vec<Value>>,
    documents: &[Document],
    packages: &Packages,
) {
    let stated: Vec<Stated> = documents
        .par_iter()
        .filter(|document| document.relative.ends_with(".py"))
        .filter_map(|document| Stated::of(document, packages))
        .collect();
    let repository = Repository::of(&stated);
    if let Some(stream) = facts.get_mut("ClassFact") {
        for fact in stream.iter_mut() {
            repository.state(fact);
        }
    }
    if let Some(stream) = facts.get_mut("FunctionFact") {
        for fact in stream.iter_mut() {
            repository.state_callable(fact);
        }
    }
}

/// What one module states about the classes it declares and the names it reaches.
struct Stated {
    module: String,
    path: String,
    is_package: bool,
    is_reexport_only: bool,
    states_policy: bool,
    declared: Vec<Declared>,
    imported: Vec<(String, String)>,
    called: BTreeSet<String>,
    read: BTreeSet<String>,
    exported: Vec<String>,
}

/// One top-level class exactly as the file declaring it writes it down.
struct Declared {
    name: String,
    bases: Vec<String>,
    line_count: usize,
    members: Vec<Member>,
    is_plain: bool,
    is_declarative: bool,
}

/// One member of a class, read for whether inheriting it twice would be a hazard.
struct Member {
    name: String,
    is_concrete: bool,
    delegates_to_super: bool,
}

/// One class, named the way the whole repository names it.
type Identity = (String, String);

impl Stated {
    fn of(document: &Document, packages: &Packages) -> Option<Self> {
        let parsed = parse_module(&document.source).ok()?;
        let module = parsed.syntax();
        let source = Source::new(&document.relative, &document.source);
        let name = packages.module_name(&document.relative);
        let is_package = document.relative.ends_with("/__init__.py");
        let (called, read) = usage(module);
        Some(Self {
            declared: declarations(&source, module),
            imported: imports(module, &name, is_package),
            is_reexport_only: is_reexport_only(module),
            states_policy: states_policy(module),
            exported: exported_names(module),
            module: name,
            path: document.relative.clone(),
            is_package,
            called,
            read,
        })
    }
}

/// Every class this repository declares, joined to every module that reaches one.
///
/// The joins a class rule asks for are all one to many over the whole tree, so each one is indexed
/// once here rather than searched per class. A repository of ten thousand modules is what makes
/// that the difference between one pass and one that never finishes.
struct Repository<'a> {
    definitions: BTreeMap<Identity, &'a Declared>,
    modules: BTreeMap<&'a str, &'a Stated>,
    paths: BTreeMap<&'a str, &'a str>,
    owners: BTreeMap<&'a str, &'a str>,
    bases: BTreeMap<Identity, Vec<Identity>>,
    subclasses: BTreeMap<Identity, Vec<Identity>>,
    importers: BTreeMap<Identity, BTreeSet<&'a str>>,
    built: BTreeSet<Identity>,
    reexported: BTreeSet<Identity>,
    reexported_names: BTreeSet<&'a str>,
    dispatched: BTreeSet<(&'a str, &'a str)>,
    coimports: BTreeMap<&'a str, Vec<(&'a str, Vec<&'a str>)>>,
    model_packages: BTreeSet<String>,
    states_policy: bool,
}

impl<'a> Repository<'a> {
    fn of(stated: &'a [Stated]) -> Self {
        let definitions: BTreeMap<Identity, &Declared> = stated
            .iter()
            .flat_map(|module| {
                module
                    .declared
                    .iter()
                    .map(|class| ((module.module.clone(), class.name.clone()), class))
            })
            .collect();
        let mut bases: BTreeMap<Identity, Vec<Identity>> = BTreeMap::new();
        let mut subclasses: BTreeMap<Identity, Vec<Identity>> = BTreeMap::new();
        for module in stated {
            for class in &module.declared {
                let held = (module.module.clone(), class.name.clone());
                let resolved: Vec<Identity> = class
                    .bases
                    .iter()
                    .filter_map(|base| resolve(module, base, &definitions))
                    .collect();
                for base in &resolved {
                    subclasses
                        .entry(base.clone())
                        .or_default()
                        .push(held.clone());
                }
                bases.insert(held, resolved);
            }
        }
        let mut repository = Self {
            modules: stated
                .iter()
                .map(|module| (module.module.as_str(), module))
                .collect(),
            paths: stated
                .iter()
                .map(|module| (module.module.as_str(), module.path.as_str()))
                .collect(),
            owners: stated
                .iter()
                .map(|module| (module.path.as_str(), module.module.as_str()))
                .collect(),
            importers: importers(stated, &definitions),
            states_policy: stated.iter().any(|module| module.states_policy),
            built: built(stated, &definitions),
            reexported: stated
                .iter()
                .filter(|module| module.is_package)
                .flat_map(|module| module.imported.iter().cloned())
                .filter(|held| definitions.contains_key(held))
                .collect(),
            reexported_names: stated
                .iter()
                .filter(|module| module.is_package)
                .flat_map(|module| module.exported.iter().map(String::as_str))
                .collect(),
            coimports: coimports(stated),
            model_packages: BTreeSet::new(),
            dispatched: BTreeSet::new(),
            definitions,
            bases,
            subclasses,
        };
        repository.dispatched = repository.dispatched_members();
        repository.model_packages = repository.model_packages();
        repository
    }

    /// Return every path and member name that some class above or below also declares.
    fn dispatched_members(&self) -> BTreeSet<(&'a str, &'a str)> {
        let mut found = BTreeSet::new();
        for (held, class) in &self.definitions {
            let Some(path) = self.paths.get(held.0.as_str()) else {
                continue;
            };
            let related: BTreeSet<&str> = self
                .ancestors(held)
                .into_iter()
                .chain(self.descendants(held))
                .filter_map(|relative| self.definitions.get(&relative))
                .flat_map(|above| above.members.iter().map(|member| member.name.as_str()))
                .collect();
            for member in &class.members {
                if let Some(shared) = related.get(member.name.as_str()) {
                    found.insert((*path, *shared));
                }
            }
        }
        found
    }

    /// Return every directory named `models` that really holds the data models of this project.
    ///
    /// A folder of neural networks is also called `models`, and a placement rule that judged one
    /// as a shared data package would report every file it holds forever.
    fn model_packages(&self) -> BTreeSet<String> {
        self.definitions
            .iter()
            .filter(|(_, class)| class.is_declarative)
            .filter_map(|(held, _)| self.paths.get(held.0.as_str()))
            .filter_map(|path| path.rsplit_once('/'))
            .filter(|(directory, _)| directory.rsplit('/').next() == Some("models"))
            .map(|(directory, _)| directory.to_string())
            .collect()
    }

    /// Write onto one file's class fact everything only the whole repository knows.
    fn state(&self, fact: &mut Value) {
        let Some(path) = fact["span"]["path"].as_str().map(str::to_string) else {
            return;
        };
        let coupled = self.coupled_groups(&path);
        let holds_models = path
            .rsplit_once('/')
            .is_some_and(|(directory, _)| self.model_packages.contains(directory));
        let Some(object) = fact.as_object_mut() else {
            return;
        };
        object.insert("coupled_groups".to_string(), json!(coupled));
        object.insert(
            "has_approved_model_foundation_policy".to_string(),
            json!(self.states_policy),
        );
        if !holds_models {
            object.insert("model_files".to_string(), json!([] as [Value; 0]));
        }
        let Some(classes) = object.get_mut("classes").and_then(Value::as_array_mut) else {
            return;
        };
        for class in classes {
            let Some(name) = class["name"].as_str().map(str::to_string) else {
                continue;
            };
            let Some(held) = self.identify(&path, &name) else {
                continue;
            };
            let stated = self.judgement(&held, class);
            if let Some(record) = class.as_object_mut() {
                for (field, value) in stated {
                    record.insert(field, value);
                }
            }
        }
    }

    /// Write onto one callable fact whether it takes part in dispatch across the repository.
    fn state_callable(&self, fact: &mut Value) {
        let (Some(path), Some(name)) = (fact["span"]["path"].as_str(), fact["name"].as_str())
        else {
            return;
        };
        if !self.dispatched.contains(&(path, name)) {
            return;
        }
        if let Some(record) = fact.as_object_mut() {
            record.insert("is_polymorphic".to_string(), json!(true));
        }
    }

    /// Return what the repository concludes about one class, field by field.
    fn judgement(&self, held: &Identity, class: &Value) -> Vec<(String, Value)> {
        let subclasses = self.subclasses.get(held).cloned().unwrap_or_default();
        let importing: Vec<&str> = self
            .importers
            .get(held)
            .map(|found| found.iter().copied().collect())
            .unwrap_or_default();
        vec![
            (
                "direct_subclasses".to_string(),
                json!(subclasses.iter().map(|(_, name)| name).collect::<Vec<_>>()),
            ),
            (
                "descendant_count".to_string(),
                json!(self.descendants(held).len()),
            ),
            ("is_instantiated".to_string(), json!(self.is_built(held))),
            (
                "is_exported".to_string(),
                json!(self.is_exported(held, class)),
            ),
            ("importing_modules".to_string(), json!(importing)),
            (
                "only_cross_module_reference_is_subclass".to_string(),
                json!(self.only_reference_is_subclass(held, &subclasses, &importing)),
            ),
            (
                "base_is_removable_overlap".to_string(),
                json!(self.base_is_removable(held)),
            ),
            (
                "has_redundant_direct_base".to_string(),
                json!(self.has_redundant_base(held)),
            ),
            (
                "has_noncooperative_concrete_collision".to_string(),
                json!(self.has_hazardous_collision(held)),
            ),
            (
                "proposed_model_destination".to_string(),
                json!(self.proposed_destination(held, &importing)),
            ),
        ]
    }

    /// Return which repository class one file's record names, when the repository knows it.
    fn identify(&self, path: &str, name: &str) -> Option<Identity> {
        let held = ((*self.owners.get(path)?).to_string(), name.to_string());
        self.definitions.contains_key(&held).then_some(held)
    }

    /// Return every class above one class, nearest first, without visiting a cycle twice.
    fn ancestors(&self, held: &Identity) -> Vec<Identity> {
        self.reachable(held, &self.bases)
    }

    /// Return every class below one class, without visiting a cycle twice.
    fn descendants(&self, held: &Identity) -> Vec<Identity> {
        self.reachable(held, &self.subclasses)
    }

    fn reachable(
        &self,
        held: &Identity,
        links: &BTreeMap<Identity, Vec<Identity>>,
    ) -> Vec<Identity> {
        let mut found = Vec::new();
        let mut seen: BTreeSet<Identity> = BTreeSet::from([held.clone()]);
        let mut pending: Vec<Identity> = links.get(held).cloned().unwrap_or_default();
        while let Some(current) = pending.pop() {
            if !seen.insert(current.clone()) {
                continue;
            }
            pending.extend(links.get(&current).cloned().unwrap_or_default());
            found.push(current);
        }
        found
    }

    /// Whether any module reaching one class ever calls its name, which builds one.
    fn is_built(&self, held: &Identity) -> bool {
        self.built.contains(held)
    }

    /// Whether one class is offered outside the module declaring it, by name or by re-export.
    fn is_exported(&self, held: &Identity, class: &Value) -> bool {
        class["is_exported"].as_bool().unwrap_or_default()
            || self.reexported.contains(held)
            || self.reexported_names.contains(held.1.as_str())
    }

    /// Whether the only place outside its own module that names one class is its one subclass.
    fn only_reference_is_subclass(
        &self,
        held: &Identity,
        subclasses: &[Identity],
        importing: &[&str],
    ) -> bool {
        let [(child, _)] = subclasses else {
            return false;
        };
        importing == [child.as_str()]
            && self
                .modules
                .get(child.as_str())
                .is_some_and(|module| !module.read.contains(&held.1))
    }

    /// Whether the one base of one class is a base the closed world rule already owns.
    fn base_is_removable(&self, held: &Identity) -> bool {
        let [only] = self.bases.get(held).map(Vec::as_slice).unwrap_or_default() else {
            return false;
        };
        let Some(base) = self.definitions.get(only) else {
            return false;
        };
        let subclasses = self.subclasses.get(only).cloned().unwrap_or_default();
        let importing: Vec<&str> = self
            .importers
            .get(only)
            .map(|found| found.iter().copied().collect())
            .unwrap_or_default();
        base.is_plain
            && self.bases.get(only).is_none_or(Vec::is_empty)
            && subclasses.len() == 1
            && self.descendants(only).len() == 1
            && !self.is_built(only)
            && !self.is_exported(only, &json!({"is_exported": false}))
            && self.only_reference_is_subclass(only, &subclasses, &importing)
    }

    /// Whether one direct base of a class already inherits another direct base of the same class.
    fn has_redundant_base(&self, held: &Identity) -> bool {
        let direct = self.bases.get(held).cloned().unwrap_or_default();
        direct.len() >= 2
            && direct.iter().any(|base| {
                self.ancestors(base)
                    .iter()
                    .any(|above| direct.contains(above))
            })
    }

    /// Whether two direct bases both supply the same member and at least one refuses to cooperate.
    fn has_hazardous_collision(&self, held: &Identity) -> bool {
        let direct = self.bases.get(held).cloned().unwrap_or_default();
        if direct.len() < 2 {
            return false;
        }
        let supplied: Vec<Vec<&Member>> = direct.iter().map(|base| self.supplies(base)).collect();
        let names: BTreeSet<&str> = supplied
            .iter()
            .flatten()
            .map(|member| member.name.as_str())
            .collect();
        names.into_iter().any(|name| {
            let providers: Vec<&&Member> = supplied
                .iter()
                .filter_map(|held| held.iter().find(|member| member.name == name))
                .collect();
            providers.len() >= 2 && providers.iter().any(|member| !member.delegates_to_super)
        })
    }

    /// Return every concrete member one base hands down, its own first and its ancestors' after.
    fn supplies(&self, base: &Identity) -> Vec<&'a Member> {
        let mut found: Vec<&Member> = Vec::new();
        for held in std::iter::once(base.clone()).chain(self.ancestors(base)) {
            let Some(class) = self.definitions.get(&held) else {
                continue;
            };
            for member in &class.members {
                if member.is_concrete && !found.iter().any(|kept| kept.name == member.name) {
                    found.push(member);
                }
            }
        }
        found
    }

    /// Return the file a reused model belongs in, given every module that imports it.
    ///
    /// Consumers inside one package propose that package's own models module, and consumers
    /// spanning packages propose one file for the class below the nearest package they share.
    fn proposed_destination(&self, held: &Identity, importing: &[&str]) -> String {
        if importing.len() < 2 {
            return String::new();
        }
        let packages: Vec<&str> = importing
            .iter()
            .map(|module| {
                module
                    .rsplit_once('.')
                    .map(|(head, _)| head)
                    .unwrap_or(module)
            })
            .collect();
        let shared = common_package(&packages);
        let Some(directory) = self.directory(&shared) else {
            return String::new();
        };
        if packages.iter().all(|package| *package == shared) {
            return format!("{directory}models.py");
        }
        format!("{directory}models/{}.py", snake_case(&held.1))
    }

    /// Return where on disk one package sits, read off any module the package holds.
    fn directory(&self, package: &str) -> Option<String> {
        self.paths
            .range(package..)
            .take_while(|(module, _)| module.starts_with(package))
            .find(|(module, _)| {
                module.len() == package.len() || module[package.len()..].starts_with('.')
            })
            .map(|(module, path)| {
                let depth = module[package.len()..].matches('.').count();
                let mut held: Vec<&str> = path.split('/').collect();
                held.truncate(held.len().saturating_sub(depth + 1));
                held.iter().map(|part| format!("{part}/")).collect()
            })
    }

    /// Return the short co-imported role types one file declares under a shared name prefix.
    fn coupled_groups(&self, path: &str) -> Vec<Value> {
        let Some(module) = self.owners.get(path).copied() else {
            return Vec::new();
        };
        let Some(stated) = self.modules.get(module) else {
            return Vec::new();
        };
        let mut grouped: BTreeMap<String, Vec<&Declared>> = BTreeMap::new();
        for class in &stated.declared {
            let words = camel_words(&class.name);
            if words.len() >= 2 {
                grouped.entry(words[0].clone()).or_default().push(class);
            }
        }
        grouped
            .into_iter()
            .filter(|(_, held)| held.len() >= 2)
            .filter_map(|(first, held)| self.coupled_group(module, &first, &held))
            .collect()
    }

    fn coupled_group(&self, module: &str, first: &str, held: &[&Declared]) -> Option<Value> {
        let words: Vec<Vec<String>> = held.iter().map(|class| camel_words(&class.name)).collect();
        let mut prefix = vec![first.to_string()];
        while words.iter().all(|held| {
            held.len() > prefix.len() + 1 && held[prefix.len()] == words[0][prefix.len()]
        }) {
            prefix.push(words[0][prefix.len()].clone());
        }
        let shared = prefix.concat();
        let suffixes: Vec<String> = held
            .iter()
            .map(|class| class.name[shared.len()..].to_string())
            .collect();
        let names: Vec<&str> = held.iter().map(|class| class.name.as_str()).collect();
        let coimporting = self
            .coimports
            .get(module)
            .map(Vec::as_slice)
            .unwrap_or_default()
            .iter()
            .filter(|(_, imported)| {
                imported.iter().filter(|name| names.contains(name)).count() >= 2
            })
            .count();
        Some(json!({
            "prefix": shared,
            "role_suffixes": suffixes,
            "type_count": held.len(),
            "maximum_type_lines": held.iter().map(|class| class.line_count).max().unwrap_or(0),
            "coimporting_module_count": coimporting,
        }))
    }
}

/// Return the class one base name reaches, through this module's imports or its own body.
fn resolve(
    module: &Stated,
    base: &str,
    definitions: &BTreeMap<Identity, &Declared>,
) -> Option<Identity> {
    let own = (module.module.clone(), base.to_string());
    if definitions.contains_key(&own) {
        return Some(own);
    }
    module
        .imported
        .iter()
        .find(|(_, name)| name == base)
        .filter(|held| definitions.contains_key(*held))
        .cloned()
}

/// Return every top-level class one module declares, read for what a class rule asks of it.
fn declarations(source: &Source, module: &ModModule) -> Vec<Declared> {
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
                line_count: source.line_count(item.range()),
                members: members(item),
                is_declarative: is_declarative(item),
                is_plain: item.decorator_list.is_empty()
                    && item
                        .arguments
                        .iter()
                        .all(|arguments| arguments.keywords.is_empty()),
            }),
            _ => None,
        })
        .collect()
}

/// Return every method one class declares, read for whether inheriting it twice is a hazard.
fn members(item: &StmtClassDef) -> Vec<Member> {
    item.body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(method) => Some(method),
            _ => None,
        })
        .map(|method| {
            let marked = method.decorator_list.iter().any(|decorator| {
                matches!(
                    last_segment(&qualified_name(&decorator.expression)),
                    "abstractmethod" | "abstractproperty" | "overload"
                )
            });
            Member {
                name: method.name.to_string(),
                is_concrete: !marked && !is_stub(&method.body),
                delegates_to_super: delegates_to_super(&method.body, method.name.as_str()),
            }
        })
        .collect()
}

/// Whether one class declares data a library validates rather than behavior it runs.
fn is_declarative(item: &StmtClassDef) -> bool {
    item.arguments
        .iter()
        .flat_map(|arguments| arguments.args.iter())
        .any(|base| {
            matches!(
                last_segment(&qualified_name(base)),
                "BaseModel"
                    | "Component"
                    | "DeclarativeBase"
                    | "FlexModel"
                    | "FrozenFlexModel"
                    | "FrozenModel"
                    | "Model"
                    | "RootModel"
                    | "SQLModel"
            )
        })
        || item
            .decorator_list
            .iter()
            .any(|decorator| last_segment(&qualified_name(&decorator.expression)) == "dataclass")
}

/// Whether one body stands in for an implementation rather than being one.
fn is_stub(body: &[Stmt]) -> bool {
    executable(body).iter().all(|statement| match statement {
        Stmt::Pass(_) => true,
        Stmt::Expr(item) => matches!(item.value.as_ref(), Expr::EllipsisLiteral(_)),
        Stmt::Raise(item) => item
            .exc
            .as_deref()
            .is_some_and(|raised| qualified_name(raised).ends_with("NotImplementedError")),
        _ => false,
    })
}

/// Whether one body hands the same member on to whatever the class was linearized behind.
fn delegates_to_super(body: &[Stmt], name: &str) -> bool {
    let mut found = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        for expression in expressions(statement) {
            descend(expression, &mut found);
        }
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    found.into_iter().any(|expression| {
        matches!(expression, Expr::Attribute(item)
            if item.attr.as_str() == name
                && matches!(item.value.as_ref(), Expr::Call(inner)
                    if qualified_name(&inner.func) == "super"))
    })
}

/// Collect one expression and every expression inside it.
fn descend<'a>(expression: &'a Expr, found: &mut Vec<&'a Expr>) {
    found.push(expression);
    for child in crate::walk::children(expression) {
        descend(child, found);
    }
}

/// Return the body a declaration runs, without the docstring that opens it.
fn executable(body: &[Stmt]) -> &[Stmt] {
    match body.split_first() {
        Some((first, rest)) if docstring(std::slice::from_ref(first)).is_some() => rest,
        _ => body,
    }
}

/// Return which names one module calls and which it names anywhere else, at any depth.
///
/// A base is the one place a class name appears without the module depending on the class for
/// anything except declaring another one, so the base list is left out of what a module reads.
/// That is exactly the difference one rule has to see to prove a base exists only for its child.
fn usage(module: &ModModule) -> (BTreeSet<String>, BTreeSet<String>) {
    let mut called = BTreeSet::new();
    let mut read = BTreeSet::new();
    for statement in walk(module) {
        if matches!(statement, Stmt::Import(_) | Stmt::ImportFrom(_)) {
            continue;
        }
        let stated: Vec<&Expr> = match statement {
            Stmt::ClassDef(item) => item
                .decorator_list
                .iter()
                .map(|decorator| &decorator.expression)
                .collect(),
            _ => expressions(statement),
        };
        let mut found = Vec::new();
        for expression in stated {
            descend(expression, &mut found);
        }
        for expression in found {
            match expression {
                Expr::Call(item) => {
                    if let Expr::Name(name) = item.func.as_ref() {
                        called.insert(name.id.to_string());
                    }
                }
                Expr::Name(name) => {
                    read.insert(name.id.to_string());
                }
                _ => {}
            }
        }
    }
    (called, read)
}

/// Return every explicit `from` import one module states, as the module and name it reaches.
fn imports(module: &ModModule, name: &str, is_package: bool) -> Vec<Identity> {
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

/// Whether this project has established which model foundation its own classes derive.
fn states_policy(module: &ModModule) -> bool {
    module.body.iter().any(|statement| match statement {
        Stmt::ImportFrom(item) => {
            item.module
                .as_ref()
                .map(ToString::to_string)
                .is_some_and(|origin| {
                    origin.split('.').next().unwrap_or(&origin) == "patos"
                        || origin.ends_with("bases")
                })
        }
        _ => false,
    })
}

/// Whether one module hands names on rather than declaring anything of its own.
fn is_reexport_only(module: &ModModule) -> bool {
    executable(&module.body)
        .iter()
        .all(|statement| match statement {
            Stmt::Import(_) | Stmt::ImportFrom(_) => true,
            Stmt::Assign(item) => item
                .targets
                .iter()
                .all(|target| matches!(target, Expr::Name(name) if name.id.as_str() == "__all__")),
            _ => false,
        })
}

/// Return the names one module lists in `__all__`, which are exported on purpose.
fn exported_names(module: &ModModule) -> Vec<String> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::Assign(item)
                if item
                    .targets
                    .iter()
                    .any(|target| matches!(target, Expr::Name(name) if name.id == "__all__")) =>
            {
                Some(&item.value)
            }
            _ => None,
        })
        .flat_map(|value| {
            let mut found = Vec::new();
            descend(value, &mut found);
            found
        })
        .filter_map(|element| match element {
            Expr::StringLiteral(literal) => Some(literal.value.to_str().to_string()),
            _ => None,
        })
        .collect()
}

/// Return every class some module reaching it ever calls, which is where one gets built.
fn built(stated: &[Stated], definitions: &BTreeMap<Identity, &Declared>) -> BTreeSet<Identity> {
    let mut found = BTreeSet::new();
    for module in stated {
        let reached = module.imported.iter().cloned().chain(
            module
                .declared
                .iter()
                .map(|class| (module.module.clone(), class.name.clone())),
        );
        for held in reached {
            if module.called.contains(&held.1) && definitions.contains_key(&held) {
                found.insert(held);
            }
        }
    }
    found
}

/// Return which ordinary modules import which names from each module, keyed by the module read.
fn coimports(stated: &[Stated]) -> BTreeMap<&str, Vec<(&str, Vec<&str>)>> {
    let mut found: BTreeMap<&str, Vec<(&str, Vec<&str>)>> = BTreeMap::new();
    for module in stated.iter().filter(|module| !module.is_package) {
        let mut taken: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
        for (origin, name) in &module.imported {
            taken
                .entry(origin.as_str())
                .or_default()
                .push(name.as_str());
        }
        for (origin, names) in taken {
            if origin != module.module {
                found
                    .entry(origin)
                    .or_default()
                    .push((module.module.as_str(), names));
            }
        }
    }
    found
}

/// Return which ordinary modules import each declared class, keyed by definition.
fn importers<'a>(
    stated: &'a [Stated],
    definitions: &BTreeMap<Identity, &Declared>,
) -> BTreeMap<Identity, BTreeSet<&'a str>> {
    let mut found: BTreeMap<Identity, BTreeSet<&str>> = BTreeMap::new();
    for module in stated {
        if module.is_package || module.is_reexport_only {
            continue;
        }
        for held in &module.imported {
            if held.0 == module.module || !definitions.contains_key(held) {
                continue;
            }
            found
                .entry(held.clone())
                .or_default()
                .insert(module.module.as_str());
        }
    }
    found
}

/// Return the longest dotted package every one of these packages sits inside.
fn common_package(packages: &[&str]) -> String {
    let Some((first, rest)) = packages.split_first() else {
        return String::new();
    };
    let mut shared: Vec<&str> = first.split('.').collect();
    for package in rest {
        let held: Vec<&str> = package.split('.').collect();
        let kept = shared
            .iter()
            .zip(held.iter())
            .take_while(|(left, right)| left == right)
            .count();
        shared.truncate(kept);
    }
    shared.join(".")
}

/// Split one class name into the words its capitals separate.
fn camel_words(name: &str) -> Vec<String> {
    let mut words: Vec<String> = Vec::new();
    for character in name.chars() {
        if character.is_uppercase() || words.is_empty() {
            words.push(String::new());
        }
        if let Some(word) = words.last_mut() {
            word.push(character);
        }
    }
    words.into_iter().filter(|word| !word.is_empty()).collect()
}

/// Return the file name a class of this name would be given.
fn snake_case(name: &str) -> String {
    camel_words(name)
        .into_iter()
        .map(|word| word.to_lowercase())
        .collect::<Vec<_>>()
        .join("_")
}

fn last_segment(name: &str) -> &str {
    name.rsplit('.').next().unwrap_or(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn enriched(sources: &[(&str, &str)]) -> Vec<Value> {
        let documents: Vec<Document> = sources
            .iter()
            .map(|(relative, source)| Document {
                relative: (*relative).to_string(),
                source: (*source).to_string(),
            })
            .collect();
        let packages = Packages::of(&documents);
        let mut facts: BTreeMap<String, Vec<Value>> = BTreeMap::from([
            ("ClassFact".to_string(), Vec::new()),
            ("FunctionFact".to_string(), Vec::new()),
        ]);
        let mut stats = crate::protocol::Stats::default();
        for document in &documents {
            crate::python::extract(document, &packages, &mut facts, &mut stats);
        }
        enrich(&mut facts, &documents, &packages);
        facts
            .remove("ClassFact")
            .unwrap_or_default()
            .into_iter()
            .flat_map(|fact| {
                fact["classes"]
                    .as_array()
                    .cloned()
                    .unwrap_or_default()
                    .into_iter()
            })
            .collect()
    }

    fn class<'a>(classes: &'a [Value], name: &str) -> &'a Value {
        classes
            .iter()
            .find(|held| held["name"] == name)
            .expect("the class is declared")
    }

    #[test]
    fn a_base_kept_only_for_one_subclass_states_every_half_of_that_proof() {
        let classes = enriched(&[
            ("shop/__init__.py", ""),
            (
                "shop/support.py",
                "class ServiceSupport:\n    def normalize(self, value):\n        return value.strip()\n",
            ),
            (
                "shop/service.py",
                "from .support import ServiceSupport\n\n\nclass Service(ServiceSupport):\n    pass\n",
            ),
        ]);
        let base = class(&classes, "ServiceSupport");

        assert_eq!(base["direct_subclasses"], json!(["Service"]));
        assert_eq!(base["descendant_count"], 1);
        assert_eq!(base["is_instantiated"], false);
        assert_eq!(base["is_exported"], false);
        assert_eq!(base["only_cross_module_reference_is_subclass"], true);
        assert_eq!(
            class(&classes, "Service")["base_is_removable_overlap"],
            true
        );
    }

    #[test]
    fn a_base_somebody_builds_or_exports_is_not_kept_only_for_its_subclass() {
        let classes = enriched(&[
            ("shop/__init__.py", "from .support import ServiceSupport\n"),
            (
                "shop/support.py",
                "class ServiceSupport:\n    def normalize(self, value):\n        return value\n",
            ),
            (
                "shop/service.py",
                "from .support import ServiceSupport\n\n\nclass Service(ServiceSupport):\n    pass\n\n\nheld = ServiceSupport()\n",
            ),
        ]);
        let base = class(&classes, "ServiceSupport");

        assert_eq!(base["is_instantiated"], true);
        assert_eq!(base["is_exported"], true);
        assert_eq!(base["only_cross_module_reference_is_subclass"], false);
    }

    #[test]
    fn two_bases_supplying_one_concrete_method_are_an_order_sensitive_hierarchy() {
        let classes = enriched(&[
            ("shop/__init__.py", ""),
            (
                "shop/loaders.py",
                "class JsonLoader:\n    def load(self):\n        return 1\n\n\nclass CachedLoader:\n    def load(self):\n        return 2\n\n\nclass Service(JsonLoader, CachedLoader):\n    pass\n\n\nclass Polite(JsonLoader, CachedLoader):\n    def load(self):\n        return super().load()\n",
            ),
        ]);

        assert_eq!(
            class(&classes, "Service")["has_noncooperative_concrete_collision"],
            true
        );
        assert_eq!(
            class(&classes, "Service")["has_redundant_direct_base"],
            false
        );
    }

    #[test]
    fn a_base_that_already_inherits_another_base_is_a_redundant_direct_edge() {
        let classes = enriched(&[
            ("shop/__init__.py", ""),
            (
                "shop/layers.py",
                "class Contract:\n    def run(self):\n        return 1\n\n\nclass Middle(Contract):\n    def other(self):\n        return 2\n\n\nclass Leaf(Middle, Contract):\n    pass\n",
            ),
        ]);

        assert_eq!(class(&classes, "Leaf")["has_redundant_direct_base"], true);
    }

    #[test]
    fn a_model_two_packages_import_proposes_the_file_below_the_package_they_share() {
        let classes = enriched(&[
            ("shop/__init__.py", ""),
            ("shop/orders/__init__.py", ""),
            ("shop/billing/__init__.py", ""),
            (
                "shop/types.py",
                "from pydantic import BaseModel\n\n\nclass OrderLine(BaseModel):\n    total: int\n",
            ),
            (
                "shop/orders/place.py",
                "from ..types import OrderLine\n\n\ndef place(line: OrderLine) -> int:\n    return line.total\n",
            ),
            (
                "shop/billing/charge.py",
                "from ..types import OrderLine\n\n\ndef charge(line: OrderLine) -> int:\n    return line.total\n",
            ),
        ]);
        let model = class(&classes, "OrderLine");

        assert_eq!(model["is_declarative_model"], true);
        assert_eq!(model["has_ordinary_behavior"], false);
        assert_eq!(
            model["importing_modules"],
            json!(["shop.billing.charge", "shop.orders.place"])
        );
        assert_eq!(
            model["proposed_model_destination"],
            "shop/models/order_line.py"
        );
    }

    #[test]
    fn a_model_one_package_imports_proposes_that_package_own_models_module() {
        let classes = enriched(&[
            ("shop/__init__.py", ""),
            ("shop/orders/__init__.py", ""),
            (
                "shop/orders/types.py",
                "from pydantic import BaseModel\n\n\nclass OrderLine(BaseModel):\n    total: int\n",
            ),
            (
                "shop/orders/place.py",
                "from .types import OrderLine\n\n\ndef place(line: OrderLine) -> int:\n    return line.total\n",
            ),
            (
                "shop/orders/audit.py",
                "from .types import OrderLine\n\n\ndef audit(line: OrderLine) -> int:\n    return line.total\n",
            ),
        ]);

        assert_eq!(
            class(&classes, "OrderLine")["proposed_model_destination"],
            "shop/orders/models.py"
        );
    }

    #[test]
    fn two_short_role_types_two_modules_import_together_propose_one_namespace() {
        let sources = [
            ("shop/__init__.py", ""),
            (
                "shop/message.py",
                "class MessageContent:\n    pass\n\n\nclass MessageKind:\n    pass\n",
            ),
            (
                "shop/api.py",
                "from .message import MessageContent, MessageKind\n\n\ndef read(content: MessageContent, kind: MessageKind) -> None:\n    return None\n",
            ),
            (
                "shop/jobs.py",
                "from .message import MessageContent, MessageKind\n\n\ndef sweep(content: MessageContent, kind: MessageKind) -> None:\n    return None\n",
            ),
        ];
        let documents: Vec<Document> = sources
            .iter()
            .map(|(relative, source)| Document {
                relative: (*relative).to_string(),
                source: (*source).to_string(),
            })
            .collect();
        let packages = Packages::of(&documents);
        let mut facts: BTreeMap<String, Vec<Value>> =
            BTreeMap::from([("ClassFact".to_string(), Vec::new())]);
        let mut stats = crate::protocol::Stats::default();
        for document in &documents {
            crate::python::extract(document, &packages, &mut facts, &mut stats);
        }
        enrich(&mut facts, &documents, &packages);
        let group = facts["ClassFact"]
            .iter()
            .flat_map(|fact| {
                fact["coupled_groups"]
                    .as_array()
                    .cloned()
                    .unwrap_or_default()
            })
            .next()
            .expect("the group is proposed");

        assert_eq!(group["prefix"], "Message");
        assert_eq!(group["role_suffixes"], json!(["Content", "Kind"]));
        assert_eq!(group["type_count"], 2);
        assert_eq!(group["coimporting_module_count"], 2);
    }

    #[test]
    fn a_class_this_repository_never_heard_of_leaves_the_record_alone() {
        let classes = enriched(&[("alone.py", "class Report:\n    pass\n")]);

        assert_eq!(class(&classes, "Report")["descendant_count"], 0);
        assert_eq!(
            class(&classes, "Report")["direct_subclasses"],
            json!([] as [&str; 0])
        );
    }
}
