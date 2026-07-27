use crate::discovery::{Document, Packages};
use crate::families;
use crate::protocol::Stats;
use crate::source::Source;
use crate::walk::{
    annotation_name, blocks, body_range, children, declared_name, docstring, expressions,
    qualified_name, walk,
};
use ruff_python_ast::token::{TokenKind, Tokens};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    Alias, Expr, ExprContext, ModModule, Parameters, Stmt, StmtClassDef, StmtFunctionDef,
};
use ruff_python_parser::parse_module;
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// Build every requested fact family from one document, parsing it exactly once.
pub fn extract(
    document: &Document,
    packages: &Packages,
    facts: &mut BTreeMap<String, Vec<Value>>,
    stats: &mut Stats,
) {
    let parsed = match parse_module(&document.source) {
        Ok(parsed) => parsed,
        Err(_) => {
            stats.parse_failure_count += 1;
            return;
        }
    };
    let source = Source::new(&document.relative, &document.source);
    let module = parsed.syntax();
    if let Some(stream) = facts.get_mut("ModuleFact") {
        stream.push(module_fact(&source, module));
    }
    if let Some(stream) = facts.get_mut("ImportBindingFact") {
        stream.extend(import_facts(&source, packages, module));
    }
    if let Some(stream) = facts.get_mut("FunctionFact") {
        stream.extend(function_facts(&source, module));
    }
    if let Some(stream) = facts.get_mut("ClassFact") {
        stream.push(class_fact(&source, module, parsed.tokens()));
    }
    if let Some(stream) = facts.get_mut("CommentFact") {
        stream.push(comment_fact(&source, parsed.tokens()));
    }
    if let Some(stream) = facts.get_mut("CallFact") {
        stream.push(call_fact(&source, module));
    }
    if let Some(stream) = facts.get_mut("SyntaxFact") {
        stream.extend(crate::syntax::declarations(&source, module, SYNTAX_DEPTH));
    }
    for (family, build) in FAMILY_BUILDERS {
        if matches!(*family, "TestFunctionFact" | "TestCaseGroupFact") && !is_test_module(&source)
        {
            continue;
        }
        if let Some(stream) = facts.get_mut(*family) {
            let key = format!("{}:{}", family.to_lowercase(), source.relative);
            stream.push(merge(
                base(&source, &key, module.range()),
                build(&source, module),
            ));
        }
    }
}

/// How far down a declaration's tree a syntax fact reaches.
///
/// Deep enough to hold a call inside a comprehension inside a branch, which is where the rules
/// that read code style actually look, and shallow enough that the tree stays cheaper to send
/// than re-parsing the file would be.
const SYNTAX_DEPTH: usize = 6;

/// Whether pytest would collect one file, which is what makes its functions tests.
fn is_test_module(source: &Source) -> bool {
    is_test_path(&source.relative)
}

/// Whether one path is a module a test runner collects rather than a module something calls.
pub fn is_test_path(relative: &str) -> bool {
    let name = relative.rsplit('/').next().unwrap_or(relative);
    name.starts_with("test_") || name.ends_with("_test.py") || name == "conftest.py"
}

/// Every family whose whole content one file produces from its parsed module.
type FamilyBuilder = fn(&Source, &ModModule) -> Value;
const FAMILY_BUILDERS: &[(&str, FamilyBuilder)] = &[
    ("AttributeAccessFact", families::attribute_accesses),
    ("BranchFact", families::branches),
    ("CollectionFact", families::collections),
    ("ComprehensionFact", families::comprehensions),
    ("EnumFact", |_, module| families::enums(module)),
    ("LiteralGroupFact", families::literal_groups),
    ("MethodGroupFact", families::method_groups),
    ("ParameterFact", families::parameters),
    ("ProseSegmentFact", |_, module| families::prose(module)),
    ("PydanticModelFact", |_, module| {
        families::pydantic_models(module)
    }),
    ("QueryFact", families::queries),
    ("RuntimeTypeCheckFact", |_, module| {
        families::runtime_checks(module)
    }),
    ("StringExpressionFact", families::strings),
    ("SymbolFact", families::symbols),
    ("TestCaseGroupFact", families::test_case_groups),
    ("TestFunctionFact", families::test_functions),
    ("TryBlockFact", families::try_blocks),
    ("TypeAnnotationFact", families::annotations),
    ("WaiverFact", families::waivers),
];

fn base(source: &Source, key: &str, range: ruff_text_size::TextRange) -> Value {
    json!({"key": key, "span": source.span(range), "language": "python"})
}

fn merge(mut left: Value, right: Value) -> Value {
    if let (Some(target), Some(extra)) = (left.as_object_mut(), right.as_object()) {
        for (name, value) in extra {
            target.insert(name.clone(), value.clone());
        }
    }
    left
}

fn module_fact(source: &Source, module: &ModModule) -> Value {
    let classes = module
        .body
        .iter()
        .filter(|item| matches!(item, Stmt::ClassDef(_)))
        .count();
    let functions = module
        .body
        .iter()
        .filter(|item| matches!(item, Stmt::FunctionDef(_)))
        .count();
    let imports_only = module.body.iter().all(|item| {
        matches!(
            item,
            Stmt::Import(_) | Stmt::ImportFrom(_) | Stmt::Assign(_)
        )
    });
    let members: Vec<Value> = module
        .body
        .iter()
        .filter_map(|item| {
            declared_name(item).map(|name| json!({"name": name, "responsibility": ""}))
        })
        .collect();
    let key = format!("module:{}", source.relative);
    merge(
        base(source, &key, module.range()),
        json!({
            "physical_line_count": source.text.lines().count(),
            "class_count": classes,
            "function_count": functions,
            "is_package_initializer": source.relative.ends_with("__init__.py"),
            "has_only_imports_and_all": imports_only,
            "members": members,
        }),
    )
}

/// What one module knows about itself while its import bindings are being built.
struct ImportContext {
    importer: String,
    references: ReferenceIndex,
    exported: Vec<String>,
}

/// One import statement as everything reading it needs to see it.
///
/// The last two answer a question the statement alone cannot. Removing a statement that still
/// binds a live name is not a repair, and an import written under a guard is there for whether it
/// succeeds rather than for the name it binds, so both travel with the statement instead of being
/// rediscovered per alias.
#[derive(Clone, Copy)]
struct ImportSite<'a> {
    statement: &'a Stmt,
    module: &'a str,
    level: u32,
    binding_count: usize,
    is_guarded: bool,
}

fn import_facts(source: &Source, packages: &Packages, module: &ModModule) -> Vec<Value> {
    let context = ImportContext {
        importer: packages.module_name(&source.relative),
        references: ReferenceIndex::of(module),
        exported: exported_names(module),
    };
    let mut facts = Vec::new();
    collect_imports(source, &context, &module.body, false, &mut facts);
    facts
}

/// Push one fact per name the imports in one block bind, carrying the guard enclosing them.
///
/// Whether an import failure is handled is a property of where the statement sits, and a
/// flattened statement list has already thrown that away, which is why this descends by hand. The
/// guard covers the protected region alone, so a fallback written in the handler is an ordinary
/// import that happens to sit beside one.
fn collect_imports(
    source: &Source,
    context: &ImportContext,
    body: &[Stmt],
    guarded: bool,
    facts: &mut Vec<Value>,
) {
    for statement in body {
        match statement {
            Stmt::Import(item) => facts.extend(item.names.iter().map(|alias| {
                let site = ImportSite {
                    statement,
                    module: alias.name.as_str(),
                    level: 0,
                    binding_count: item.names.len(),
                    is_guarded: guarded,
                };
                import_fact(source, context, alias, site)
            })),
            Stmt::ImportFrom(item) => {
                let named = item
                    .module
                    .as_ref()
                    .map(ruff_python_ast::Identifier::as_str);
                facts.extend(item.names.iter().map(|alias| {
                    let site = ImportSite {
                        statement,
                        module: named.unwrap_or_default(),
                        level: item.level,
                        binding_count: item.names.len(),
                        is_guarded: guarded,
                    };
                    import_fact(source, context, alias, site)
                }));
            }
            Stmt::Try(item) => {
                let handled = guarded || guards_import_failure(item);
                collect_imports(source, context, &item.body, handled, facts);
                for handler in &item.handlers {
                    let ruff_python_ast::ExceptHandler::ExceptHandler(held) = handler;
                    collect_imports(source, context, &held.body, guarded, facts);
                }
                collect_imports(source, context, &item.orelse, guarded, facts);
                collect_imports(source, context, &item.finalbody, guarded, facts);
            }
            _ => {
                for block in blocks(statement) {
                    collect_imports(source, context, block, guarded, facts);
                }
            }
        }
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
    let key = format!("import:{}:{}", source.relative, bound);
    merge(
        base(source, &key, site.statement.range()),
        json!({
            "name": bound,
            "module": site.module,
            "imported_name": imported,
            "importer_module": context.importer,
            "declaration": source.node_of("import", site.statement),
            "module_node": source.node_of("module", site.statement),
            "reference_count": references,
            "has_qualifying_use": references > 0,
            "has_documented_side_effect": site.is_guarded,
            "is_sole_binding": site.binding_count == 1,
            "is_relative": site.level > 0,
            "is_project_owned": site.level > 0 || root == project,
            "is_external": site.level == 0 && root != project,
            "is_wildcard": imported == "*",
            "is_reexported": context.exported.contains(&bound)
                || alias.asname.as_ref().map(ToString::to_string).as_deref()
                    == Some(imported.as_str()),
            "is_private_member": imported.starts_with('_') && !imported.starts_with("__"),
            "has_private_module_component": site.module.split('.').any(|part| {
                part.starts_with('_') && !part.starts_with("__")
            }),
        }),
    )
}

/// Return the names one module lists in `__all__`, which are exported on purpose.
///
/// A module states its public surface once and then adds to it, so a name reached through `+=`,
/// through an annotated assignment, or from inside a branch is exported exactly as much as one in
/// the first list. Every string the stated value holds counts, which is what keeps a list built
/// out of other lists readable.
fn exported_names(module: &ModModule) -> Vec<String> {
    let mut exported = Vec::new();
    for statement in walk(module) {
        let stated = match statement {
            Stmt::Assign(item) if item.targets.iter().any(is_dunder_all) => {
                Some(item.value.as_ref())
            }
            Stmt::AugAssign(item) if is_dunder_all(&item.target) => Some(item.value.as_ref()),
            Stmt::AnnAssign(item) if is_dunder_all(&item.target) => item.value.as_deref(),
            _ => None,
        };
        if let Some(value) = stated {
            collect_strings(value, &mut exported);
        }
    }
    exported
}

/// Collect every string one expression states, however deeply the expression nests them.
fn collect_strings(expression: &Expr, found: &mut Vec<String>) {
    if let Expr::StringLiteral(literal) = expression {
        found.push(literal.value.to_str().to_string());
    }
    for child in children(expression) {
        collect_strings(child, found);
    }
}

fn is_dunder_all(target: &Expr) -> bool {
    matches!(target, Expr::Name(name) if name.id.as_str() == "__all__")
}

fn function_facts(source: &Source, module: &ModModule) -> Vec<Value> {
    let mut facts = Vec::new();
    let asyncio = Asyncio::of(module);
    collect_functions(source, &module.body, None, "module", &asyncio, &mut facts);
    let sites = call_sites(source, module);
    let loads = ReferenceIndex::of(module).loads;
    for fact in &mut facts {
        let Some(name) = fact["name"].as_str().map(str::to_string) else {
            continue;
        };
        let called = sites.get(&name).map(Vec::as_slice).unwrap_or_default();
        let Some(object) = fact.as_object_mut() else {
            continue;
        };
        object.insert("reference_count".to_string(), json!(called.len()));
        object.insert(
            "references".to_string(),
            json!(called.iter().map(|site| &site.node).collect::<Vec<_>>()),
        );
        object.insert(
            "is_first_class_reference".to_string(),
            json!(loads.get(&name).copied().unwrap_or_default() > called.len()),
        );
        object.insert(
            "sole_reference_owner_class".to_string(),
            json!(match called {
                [only] => only.owner.as_str(),
                _ => "",
            }),
        );
    }
    facts
}

/// One place a module calls a name, and the class whose method body holds that call.
///
/// The owner is what separates a helper one class already behaves through from a helper the
/// module decomposes itself with, and it is empty for every call a class does not hold.
struct CallSite {
    node: Value,
    owner: String,
}

/// Where in one file a call sits, which is what decides whether a class owns it.
#[derive(Clone, Copy)]
struct Placement<'a> {
    owner: &'a str,
    is_inside_callable: bool,
}

impl<'a> Placement<'a> {
    /// Return where the body of one class sits, which is directly inside that class.
    fn inside_class(name: &'a str) -> Self {
        Self {
            owner: name,
            is_inside_callable: false,
        }
    }

    /// Return where the body of one callable sits, given where the callable itself sits.
    ///
    /// A method keeps the class that declares it, and a function nested inside that method loses
    /// it, because a class cannot own behavior a closure captured.
    fn inside_callable(self) -> Self {
        Self {
            owner: if self.is_inside_callable {
                ""
            } else {
                self.owner
            },
            is_inside_callable: true,
        }
    }
}

/// Index every call site in one module by the bare name it calls.
///
/// A fix that inlines a helper has to name each place the helper is called, and inside one module
/// that is exactly the set of calls whose callee is its name. A caller in another module is a
/// different question, which the repository graph answers.
fn call_sites(source: &Source, module: &ModModule) -> BTreeMap<String, Vec<CallSite>> {
    let mut sites: BTreeMap<String, Vec<CallSite>> = BTreeMap::new();
    let placement = Placement {
        owner: "",
        is_inside_callable: false,
    };
    index_calls(source, &module.body, placement, &mut sites);
    sites
}

fn index_calls(
    source: &Source,
    body: &[Stmt],
    placement: Placement<'_>,
    sites: &mut BTreeMap<String, Vec<CallSite>>,
) {
    for statement in body {
        for expression in expressions(statement) {
            index_call_expressions(source, expression, placement, sites);
        }
        match statement {
            Stmt::ClassDef(item) => index_calls(
                source,
                &item.body,
                Placement::inside_class(&item.name),
                sites,
            ),
            Stmt::FunctionDef(item) => {
                index_calls(source, &item.body, placement.inside_callable(), sites);
            }
            _ => {
                for block in blocks(statement) {
                    index_calls(source, block, placement, sites);
                }
            }
        }
    }
}

fn index_call_expressions(
    source: &Source,
    expression: &Expr,
    placement: Placement<'_>,
    sites: &mut BTreeMap<String, Vec<CallSite>>,
) {
    if let Expr::Call(item) = expression
        && let Expr::Name(name) = item.func.as_ref()
    {
        sites
            .entry(name.id.to_string())
            .or_default()
            .push(CallSite {
                node: json!(source.node_of("reference", item)),
                owner: placement.owner.to_string(),
            });
    }
    for child in children(expression) {
        index_call_expressions(source, child, placement, sites);
    }
}

/// Return the single expression one body evaluates, when the body is exactly that.
fn body_expression(source: &Source, body: &[Stmt]) -> Option<Value> {
    match body {
        [Stmt::Return(item)] => item
            .value
            .as_ref()
            .map(|value| json!(source.node("expression", value.range()))),
        [Stmt::Expr(item)] => Some(json!(source.node("expression", item.value.range()))),
        _ => None,
    }
}

fn collect_functions<'a>(
    source: &Source,
    body: &'a [Stmt],
    owner: Option<&'a StmtClassDef>,
    scope: &str,
    asyncio: &Asyncio,
    facts: &mut Vec<Value>,
) {
    for statement in body {
        match statement {
            Stmt::FunctionDef(item) => {
                facts.push(Callable::new(source, item, owner, scope, asyncio).fact(statement));
                collect_functions(source, &item.body, None, "nested", asyncio, facts);
            }
            Stmt::ClassDef(item) => {
                collect_functions(source, &item.body, Some(item), "method", asyncio, facts);
            }
            _ => {}
        }
    }
}

/// How one file spells the asyncio entry points a structured concurrency rule reads.
///
/// A project of its own can declare a function called `create_task`, and reading a bare name would
/// report every call to it as scheduling on the event loop. Only the names this file actually
/// bound to `asyncio` count, whether it imported the module or the entry points themselves.
struct Asyncio {
    creators: BTreeSet<String>,
    gathers: BTreeSet<String>,
    groups: BTreeSet<String>,
}

impl Asyncio {
    fn of(module: &ModModule) -> Self {
        let mut held = Self {
            creators: BTreeSet::new(),
            gathers: BTreeSet::new(),
            groups: BTreeSet::new(),
        };
        for statement in walk(module) {
            match statement {
                Stmt::Import(item) => {
                    for alias in item
                        .names
                        .iter()
                        .filter(|alias| alias.name.as_str() == "asyncio")
                    {
                        let bound = alias
                            .asname
                            .as_ref()
                            .map(ToString::to_string)
                            .unwrap_or_else(|| "asyncio".to_string());
                        held.creators.insert(format!("{bound}.create_task"));
                        held.creators.insert(format!("{bound}.ensure_future"));
                        held.gathers.insert(format!("{bound}.gather"));
                        held.groups.insert(format!("{bound}.TaskGroup"));
                    }
                }
                Stmt::ImportFrom(item)
                    if item
                        .module
                        .as_ref()
                        .is_some_and(|named| named.as_str() == "asyncio") =>
                {
                    for alias in &item.names {
                        let bound = alias
                            .asname
                            .as_ref()
                            .map(ToString::to_string)
                            .unwrap_or_else(|| alias.name.to_string());
                        match alias.name.as_str() {
                            "create_task" | "ensure_future" => held.creators.insert(bound),
                            "gather" => held.gathers.insert(bound),
                            "TaskGroup" => held.groups.insert(bound),
                            _ => false,
                        };
                    }
                }
                _ => {}
            }
        }
        held
    }
}

/// Names a decorator carries to say how the language binds a member rather than who calls it.
const BINDING_DECORATORS: &[&str] = &[
    "abstractmethod",
    "abstractproperty",
    "cache",
    "cached_property",
    "classmethod",
    "deleter",
    "final",
    "getter",
    "lru_cache",
    "override",
    "overload",
    "property",
    "setter",
    "staticmethod",
];

/// Names the language and the model libraries call rather than the code around them.
const LIFECYCLE_NAMES: &[&str] = &[
    "__init_subclass__",
    "__post_init__",
    "model_post_init",
    "setUp",
    "setUpClass",
    "setup_method",
    "tearDown",
    "tearDownClass",
    "teardown_method",
];

/// Bases whose subclasses declare data a library validates rather than behavior they run.
const MODEL_FOUNDATIONS: &[&str] = &[
    "BaseModel",
    "Component",
    "FlexModel",
    "FrozenFlexModel",
    "FrozenModel",
    "Model",
    "RootModel",
    "SQLModel",
];

/// What a hand written factory raises where a declared field would have raised for it.
const VALIDATION_EXCEPTIONS: &[&str] = &[
    "PydanticCustomError",
    "TypeError",
    "ValidationError",
    "ValueError",
];

/// Decorators that hand one member to a model library to run as validation.
const VALIDATOR_DECORATORS: &[&str] = &[
    "field_validator",
    "model_validator",
    "root_validator",
    "validator",
];

/// Types whose values carry a shape and an element type a caller has to be told about.
const TENSOR_TYPES: &[&str] = &["Array", "DeviceArray", "NDArray", "Tensor", "ndarray"];

/// The jaxtyping wrappers that state a dtype and a shape inside the annotation itself.
const TENSOR_ANNOTATIONS: &[&str] = &[
    "BFloat16",
    "Bool",
    "Complex",
    "Complex64",
    "Complex128",
    "Float",
    "Float16",
    "Float32",
    "Float64",
    "Inexact",
    "Int",
    "Int16",
    "Int32",
    "Int64",
    "Int8",
    "Integer",
    "Key",
    "Num",
    "Real",
    "Shaped",
    "UInt8",
];

/// What a docstring says when it has named the element type of a tensor.
const DTYPE_WORDS: &[&str] = &[
    "bfloat16",
    "complex128",
    "complex64",
    "dtype",
    "float16",
    "float32",
    "float64",
    "int16",
    "int32",
    "int64",
    "int8",
    "uint8",
];

/// One callable read as the evidence a rule judges rather than as the syntax that states it.
///
/// Everything answered here is answered from the file that declares the callable, which is what
/// one parse can see. Who reaches it from another module is a question for the repository graph,
/// and the two fields that ask it are attached after every file has been read.
struct Callable<'a> {
    source: &'a Source,
    item: &'a StmtFunctionDef,
    owner: Option<&'a StmtClassDef>,
    scope: &'a str,
    asyncio: &'a Asyncio,
    decorators: Vec<String>,
    body: &'a [Stmt],
}

impl<'a> Callable<'a> {
    fn new(
        source: &'a Source,
        item: &'a StmtFunctionDef,
        owner: Option<&'a StmtClassDef>,
        scope: &'a str,
        asyncio: &'a Asyncio,
    ) -> Self {
        Self {
            source,
            item,
            owner,
            scope,
            asyncio,
            decorators: decorator_texts(source, &item.decorator_list),
            body: executable(&item.body),
        }
    }

    /// State one callable as the fact every function rule reads.
    fn fact(&self, statement: &Stmt) -> Value {
        let name = self.item.name.to_string();
        let increments = control_increments(&self.item.body, 0);
        let key = format!("function:{}:{}", self.source.relative, name);
        let tensors = self.tensor_roles();
        merge(
            base(self.source, &key, statement.range()),
            json!({
                "name": name,
                "scope": self.scope,
                "visibility": visibility(&name, self.scope),
                "is_protocol_name": is_protocol_name(&name),
                "is_async": self.item.is_async,
                "implementation_lines": self.implementation_lines(),
                // The docstring is not a statement the callable runs, and all three rules reading
                // this count say so in their own definitions, so it is left out of the count.
                "direct_statement_count": self.body.len(),
                "conditional_count": increments
                    .iter()
                    .filter(|value| value["kind"] == "conditional")
                    .count(),
                "control_increments": increments,
                "parameters": parameters(&self.item.parameters),
                "decorators": self.decorators,
                "definition": self.source.node_of("function", statement),
                "body_expression": body_expression(self.source, &self.item.body),
                "docstring": docstring(&self.item.body).unwrap_or_default(),
                "is_pass_body": self.body.len() == 1 && matches!(self.body[0], Stmt::Pass(_)),
                "is_raise_body": self.body.len() == 1 && matches!(self.body[0], Stmt::Raise(_)),
                "is_property": self.wears(&["property", "cached_property", "setter", "getter", "deleter"]),
                "is_abstract": self.wears(&["abstractmethod", "abstractproperty"]),
                "is_overload": self.wears(&["overload"]),
                "is_polymorphic": self.wears(&["override"]),
                "is_pydantic_validator": self.wears(VALIDATOR_DECORATORS),
                "cache_decorator": self.cache_decorator(),
                "is_framework_hook": self.is_framework_hook(),
                "is_protocol_member": self.owner_bases().iter().any(|base| base == "Protocol"),
                "is_model_method": self
                    .owner_bases()
                    .iter()
                    .any(|base| MODEL_FOUNDATIONS.contains(&base.as_str())),
                "is_recursive": self.is_recursive(),
                "reads_receiver": self.reads_receiver(),
                "behavior_operation_count": self
                    .expressions()
                    .iter()
                    .filter(|expression| is_behavior(expression))
                    .count(),
                "returns_single_call": self.returned_call().is_some(),
                "forwards_only_parameter_unchanged": self.forwards_only_parameter(),
                "checks_raw_input_type": self.checks_raw_input_type(),
                "raises_validation_exception": self.raises_validation_exception(),
                "constructs_owner_model": self.constructs_owner_model(),
                "created_task_count": self.creations().len(),
                "has_task_group": self
                    .expressions()
                    .iter()
                    .any(|expression| self.asyncio.groups.contains(&qualified_name(expression))),
                "gather_returns_exceptions": self.gather_returns_exceptions(),
                "gather_consumes_created_tasks": self.gather_consumes_created_tasks(),
                "recognized_tensor_roles": tensors.roles,
                "has_tensor_shape_semantics": tensors.states_shape,
                "has_tensor_dtype_semantics": tensors.states_dtype,
            }),
        )
    }

    /// Count the physical source lines that execute, outside documentation and comments.
    fn implementation_lines(&self) -> usize {
        if self.body.is_empty() {
            return 0;
        }
        self.source
            .slice(body_range(self.body))
            .lines()
            .filter(|line| {
                let code = line.trim();
                !code.is_empty() && !code.starts_with('#')
            })
            .count()
    }

    /// Whether this callable wears one of the named decorators, however it was imported.
    fn wears(&self, names: &[&str]) -> bool {
        self.decorators
            .iter()
            .any(|decorator| names.contains(&decorator_name(decorator)))
    }

    /// Return the cache this callable is stored in, when a decorator puts it in one.
    fn cache_decorator(&self) -> &'static str {
        ["cached_property", "cache", "lru_cache"]
            .into_iter()
            .find(|named| self.wears(&[named]))
            .unwrap_or_default()
    }

    /// Whether something other than this project's own code decides when this callable runs.
    ///
    /// A decorator is the framework, since applying one hands the callable to whatever wrote it,
    /// and the names a language or a model library reserves are called the same way.
    fn is_framework_hook(&self) -> bool {
        let name = self.item.name.as_str();
        self.decorators
            .iter()
            .any(|decorator| !BINDING_DECORATORS.contains(&decorator_name(decorator)))
            || LIFECYCLE_NAMES.contains(&name)
            || name.starts_with("visit_")
            || name == "generic_visit"
    }

    /// Return the plain name of every base the class holding this callable states.
    fn owner_bases(&self) -> Vec<String> {
        self.owner
            .map(|owner| base_names(self.source, owner))
            .unwrap_or_default()
    }

    /// Return the name this callable binds its receiver to, when it takes one at all.
    fn receiver(&self) -> Option<&str> {
        let first = self
            .item
            .parameters
            .posonlyargs
            .first()
            .or_else(|| self.item.parameters.args.first())?;
        let name = first.parameter.name.as_str();
        (self.owner.is_some() && matches!(name, "self" | "cls") && !self.wears(&["staticmethod"]))
            .then_some(name)
    }

    /// Whether the executable body ever reads the instance or class it was handed.
    fn reads_receiver(&self) -> bool {
        self.receiver().is_some_and(|receiver| self.loads(receiver))
    }

    /// Whether the executable body calls this callable by its own name.
    fn is_recursive(&self) -> bool {
        let name = self.item.name.as_str();
        let receiver = self.receiver().unwrap_or_default();
        self.calls().iter().any(|call| {
            let called = qualified_name(&call.func);
            called == name || (!receiver.is_empty() && called == format!("{receiver}.{name}"))
        })
    }

    /// Whether any expression in the executable body loads one name.
    fn loads(&self, name: &str) -> bool {
        self.expressions()
            .iter()
            .any(|expression| matches!(expression, Expr::Name(held) if held.id.as_str() == name))
    }

    /// Return every expression the executable body evaluates, at any depth.
    fn expressions(&self) -> Vec<&'a Expr> {
        let mut found = Vec::new();
        let mut pending: Vec<&Stmt> = self.body.iter().rev().collect();
        while let Some(statement) = pending.pop() {
            for expression in expressions(statement) {
                descend(expression, &mut found);
            }
            for block in blocks(statement) {
                pending.extend(block.iter().rev());
            }
        }
        found
    }

    /// Return every call the executable body makes, at any depth.
    fn calls(&self) -> Vec<&'a ruff_python_ast::ExprCall> {
        self.expressions()
            .into_iter()
            .filter_map(|expression| match expression {
                Expr::Call(call) => Some(call),
                _ => None,
            })
            .collect()
    }

    /// Return every call in the executable body whose callee ends in one of these names.
    fn calls_named(&self, names: &[&str]) -> Vec<&'a ruff_python_ast::ExprCall> {
        self.calls()
            .into_iter()
            .filter(|call| {
                let called = qualified_name(&call.func);
                names.contains(&called.rsplit('.').next().unwrap_or(&called))
            })
            .collect()
    }

    /// Return every call in the executable body that schedules work on the event loop.
    fn creations(&self) -> Vec<&'a ruff_python_ast::ExprCall> {
        self.calls_spelled(&self.asyncio.creators)
    }

    /// Return every call whose callee this file bound to one of the named asyncio entry points.
    fn calls_spelled(&self, spellings: &BTreeSet<String>) -> Vec<&'a ruff_python_ast::ExprCall> {
        self.calls()
            .into_iter()
            .filter(|call| spellings.contains(&qualified_name(&call.func)))
            .collect()
    }

    /// Return the one call the executable body hands back, when handing it back is all it does.
    fn returned_call(&self) -> Option<&'a ruff_python_ast::ExprCall> {
        match self.body {
            [Stmt::Return(item)] => match item.value.as_deref()? {
                Expr::Call(call) => Some(call),
                _ => None,
            },
            _ => None,
        }
    }

    /// Whether this callable takes one argument and hands it to one call exactly as it arrived.
    fn forwards_only_parameter(&self) -> bool {
        let required: Vec<&str> = self
            .item
            .parameters
            .posonlyargs
            .iter()
            .chain(self.item.parameters.args.iter())
            .map(|declared| declared.parameter.name.as_str())
            .filter(|name| Some(*name) != self.receiver())
            .collect();
        let Some(call) = self.returned_call() else {
            return false;
        };
        matches!(
            (required.as_slice(), call.arguments.args.as_ref()),
            ([only], [Expr::Name(passed)]) if passed.id.as_str() == *only
        ) && call.arguments.keywords.is_empty()
    }

    /// Whether the body checks the runtime type of something a caller handed it.
    fn checks_raw_input_type(&self) -> bool {
        let taken: Vec<&str> = self
            .item
            .parameters
            .iter()
            .map(|declared| declared.name().as_str())
            .collect();
        self.calls_named(&["isinstance", "issubclass"])
            .iter()
            .filter_map(|call| call.arguments.args.first())
            .any(|checked| taken.contains(&root_name(checked)))
    }

    /// Whether the body raises what a declared field would have raised for it.
    fn raises_validation_exception(&self) -> bool {
        statements(self.body).iter().any(|statement| {
            matches!(statement, Stmt::Raise(raised) if raised
                .exc
                .as_deref()
                .map(qualified_name)
                .is_some_and(|named| VALIDATION_EXCEPTIONS
                    .contains(&named.rsplit('.').next().unwrap_or(&named))))
        })
    }

    /// Whether the body builds the very class that declares it.
    fn constructs_owner_model(&self) -> bool {
        let Some(owner) = self.owner else {
            return false;
        };
        let receiver = self.receiver().unwrap_or_default();
        self.calls().iter().any(|call| {
            let called = qualified_name(&call.func);
            called == owner.name.as_str() || (receiver == "cls" && called == "cls")
        })
    }

    /// Whether any awaited gather in the body was told to hand failures back as values.
    fn gather_returns_exceptions(&self) -> bool {
        self.calls_spelled(&self.asyncio.gathers)
            .iter()
            .any(|call| {
                call.arguments.keywords.iter().any(|keyword| {
                    keyword
                        .arg
                        .as_ref()
                        .is_some_and(|name| name == "return_exceptions")
                        && matches!(&keyword.value, Expr::BooleanLiteral(held) if held.value)
                })
            })
    }

    /// Whether a gather in the body waits on the very tasks this callable created.
    ///
    /// Both shapes a reader writes arrive here. The tasks are gathered where they were made, or
    /// they were bound to a name first and the gather names that binding instead.
    fn gather_consumes_created_tasks(&self) -> bool {
        let created = self.created_task_bindings();
        self.calls_spelled(&self.asyncio.gathers)
            .iter()
            .any(|call| {
                call.arguments.args.iter().any(|argument| {
                    let mut held = Vec::new();
                    descend(argument, &mut held);
                    held.iter().any(|inner| self.creates_task(inner))
                        || created.contains(&root_name(argument).to_string())
                })
            })
    }

    /// Whether one expression is a call this file bound to an asyncio task creator.
    fn creates_task(&self, expression: &Expr) -> bool {
        matches!(expression, Expr::Call(call)
            if self.asyncio.creators.contains(&qualified_name(&call.func)))
    }

    /// Return every name the body binds to a task it created, however it collected them.
    fn created_task_bindings(&self) -> Vec<String> {
        let mut bound = Vec::new();
        for statement in statements(self.body) {
            let (targets, value) = match statement {
                Stmt::Assign(item) => (item.targets.iter().collect::<Vec<_>>(), &item.value),
                Stmt::AnnAssign(item) => match item.value.as_ref() {
                    Some(value) => (vec![item.target.as_ref()], value),
                    None => continue,
                },
                _ => continue,
            };
            let mut held = Vec::new();
            descend(value, &mut held);
            if held.iter().any(|inner| self.creates_task(inner)) {
                bound.extend(
                    targets
                        .into_iter()
                        .map(|target| root_name(target).to_string()),
                );
            }
        }
        bound.extend(
            self.calls_named(&["append"])
                .iter()
                .filter(|call| {
                    call.arguments
                        .args
                        .iter()
                        .any(|argument| self.creates_task(argument))
                })
                .map(|call| root_name(&call.func).to_string()),
        );
        bound
    }

    /// Return which parameters and returns carry a tensor, and what the callable says about them.
    fn tensor_roles(&self) -> TensorSemantics {
        let annotated: Vec<(String, &Expr)> = self
            .item
            .parameters
            .iter()
            .filter_map(|declared| {
                declared
                    .annotation()
                    .map(|annotation| (declared.name().to_string(), annotation))
            })
            .chain(
                self.item
                    .returns
                    .as_deref()
                    .map(|annotation| ("return".to_string(), annotation)),
            )
            .filter(|(_, annotation)| is_tensor_annotation(annotation))
            .collect();
        let documentation = docstring(&self.item.body)
            .unwrap_or_default()
            .to_lowercase();
        let wrappers: Vec<String> = annotated
            .iter()
            .filter_map(|(_, annotation)| tensor_wrapper(annotation))
            .collect();
        TensorSemantics {
            states_shape: !annotated.is_empty()
                && (documentation.contains("shape")
                    || documentation.contains("dimension")
                    || !wrappers.is_empty()),
            states_dtype: !annotated.is_empty()
                && (DTYPE_WORDS.iter().any(|word| documentation.contains(word))
                    || wrappers.iter().any(|wrapper| wrapper != "Shaped")),
            roles: annotated.into_iter().map(|(role, _)| role).collect(),
        }
    }
}

/// What one callable states about the tensors it takes and hands back.
struct TensorSemantics {
    roles: Vec<String>,
    states_shape: bool,
    states_dtype: bool,
}

/// Return the body one callable runs, without the docstring that opens it.
fn executable(body: &[Stmt]) -> &[Stmt] {
    match body {
        [first, rest @ ..] if docstring(std::slice::from_ref(first)).is_some() => rest,
        _ => body,
    }
}

/// Return every statement one body holds, including the ones its blocks hold.
fn statements(body: &[Stmt]) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

/// Collect one expression and every expression inside it.
fn descend<'a>(expression: &'a Expr, found: &mut Vec<&'a Expr>) {
    found.push(expression);
    for child in children(expression) {
        descend(child, found);
    }
}

/// Whether one expression does something rather than merely naming something.
fn is_behavior(expression: &Expr) -> bool {
    matches!(
        expression,
        Expr::Await(_)
            | Expr::BinOp(_)
            | Expr::BoolOp(_)
            | Expr::Call(_)
            | Expr::Compare(_)
            | Expr::DictComp(_)
            | Expr::Generator(_)
            | Expr::If(_)
            | Expr::ListComp(_)
            | Expr::Named(_)
            | Expr::SetComp(_)
            | Expr::UnaryOp(_)
            | Expr::Yield(_)
            | Expr::YieldFrom(_)
    )
}

/// Return the exact text of every decorator one declaration wears.
fn decorator_texts(source: &Source, decorators: &[ruff_python_ast::Decorator]) -> Vec<String> {
    decorators
        .iter()
        .map(|decorator| source.slice(decorator.expression.range()).to_string())
        .collect()
}

/// Return what one decorator is called, without the module that owns it or the arguments it took.
fn decorator_name(text: &str) -> &str {
    let applied = text.split('(').next().unwrap_or(text).trim();
    applied.rsplit('.').next().unwrap_or(applied)
}

/// Return the plain name of every base one class states, without a module path or a type argument.
fn base_names(source: &Source, item: &StmtClassDef) -> Vec<String> {
    item.arguments
        .as_ref()
        .map(|arguments| {
            arguments
                .args
                .iter()
                .map(|argument| base_name(source.slice(argument.range())).to_string())
                .collect()
        })
        .unwrap_or_default()
}

/// Return what one base is called, without its module path, its type arguments, or its call.
fn base_name(text: &str) -> &str {
    let named = text
        .split(['[', '('])
        .next()
        .unwrap_or(text)
        .trim()
        .trim_end_matches('.');
    named.rsplit('.').next().unwrap_or(named)
}

/// Return the name one expression is rooted in, which is the object every access starts from.
fn root_name(expression: &Expr) -> &str {
    match expression {
        Expr::Name(name) => name.id.as_str(),
        Expr::Attribute(item) => root_name(&item.value),
        Expr::Subscript(item) => root_name(&item.value),
        Expr::Call(item) => root_name(&item.func),
        Expr::Starred(item) => root_name(&item.value),
        Expr::Await(item) => root_name(&item.value),
        _ => "",
    }
}

/// Whether one annotation names a value carrying a shape and an element type.
fn is_tensor_annotation(annotation: &Expr) -> bool {
    let mut held = Vec::new();
    descend(annotation, &mut held);
    held.iter().any(|expression| {
        let named = annotation_name(expression);
        TENSOR_TYPES.contains(&named.as_str())
    }) || tensor_wrapper(annotation).is_some()
}

/// Return the jaxtyping wrapper one annotation states, which names a dtype and a shape at once.
fn tensor_wrapper(annotation: &Expr) -> Option<String> {
    let Expr::Subscript(item) = annotation else {
        return None;
    };
    let named = annotation_name(&item.value);
    let mut held = Vec::new();
    descend(&item.slice, &mut held);
    let states_dimensions = held
        .iter()
        .any(|inner| matches!(inner, Expr::StringLiteral(_)));
    (TENSOR_ANNOTATIONS.contains(&named.as_str()) && states_dimensions).then_some(named)
}

fn visibility(name: &str, scope: &str) -> &'static str {
    if is_protocol_name(name) {
        return "public";
    }
    if name.starts_with("__") {
        return "private";
    }
    if name.starts_with('_') {
        return if scope == "method" {
            "protected"
        } else {
            "internal"
        };
    }
    "public"
}

fn is_protocol_name(name: &str) -> bool {
    name.starts_with("__") && name.ends_with("__")
}

fn parameters(parameters: &Parameters) -> Vec<Value> {
    let mut declared = Vec::new();
    for (index, parameter) in parameters.posonlyargs.iter().enumerate() {
        declared.push(parameter_fact(parameter, true, false, index == 0));
    }
    let offset = parameters.posonlyargs.len();
    for (index, parameter) in parameters.args.iter().enumerate() {
        let receiver = offset == 0 && index == 0;
        declared.push(parameter_fact(parameter, false, false, receiver));
    }
    for parameter in &parameters.kwonlyargs {
        declared.push(parameter_fact(parameter, false, true, false));
    }
    declared
}

fn parameter_fact(
    declared: &ruff_python_ast::ParameterWithDefault,
    positional_only: bool,
    keyword_only: bool,
    first: bool,
) -> Value {
    let parameter = &declared.parameter;
    let name = parameter.name.to_string();
    let receiver = first && (name == "self" || name == "cls");
    json!({
        "name": name,
        "type_name": parameter
            .annotation
            .as_ref()
            .map(|annotation| annotation_name(annotation))
            .unwrap_or_default(),
        "is_positional_only": positional_only,
        "is_keyword_only": keyword_only,
        "is_receiver": receiver,
        "is_required_by_external_contract": !receiver && declared.default().is_none(),
        "has_boolean_annotation": parameter
            .annotation
            .as_ref()
            .is_some_and(|annotation| annotation_name(annotation) == "bool"),
        "has_boolean_default": matches!(declared.default(), Some(Expr::BooleanLiteral(_))),
    })
}

fn control_increments(body: &[Stmt], depth: usize) -> Vec<Value> {
    let mut increments = Vec::new();
    for statement in body {
        let (kind, nested): (Option<&str>, Vec<&[Stmt]>) = match statement {
            Stmt::If(item) => (Some("conditional"), vec![&item.body]),
            Stmt::For(item) => (Some("loop"), vec![&item.body, &item.orelse]),
            Stmt::While(item) => (Some("loop"), vec![&item.body, &item.orelse]),
            Stmt::With(item) => (None, vec![&item.body]),
            Stmt::Match(_) => (Some("switch"), vec![]),
            Stmt::Try(item) => (
                Some("catch"),
                vec![&item.body, &item.orelse, &item.finalbody],
            ),
            _ => (None, vec![]),
        };
        if let Some(kind) = kind {
            increments.push(json!({"kind": kind, "nesting_depth": depth}));
        }
        let inner = if kind.is_some() { depth + 1 } else { depth };
        for block in nested {
            increments.extend(control_increments(block, inner));
        }
        if let Stmt::If(item) = statement {
            for clause in &item.elif_else_clauses {
                increments.push(json!({"kind": "alternative", "nesting_depth": depth}));
                increments.extend(control_increments(&clause.body, inner));
            }
        }
        if let Stmt::Match(item) = statement {
            for case in &item.cases {
                increments.extend(control_increments(&case.body, inner));
            }
        }
        if let Stmt::Try(item) = statement {
            for handler in &item.handlers {
                let ruff_python_ast::ExceptHandler::ExceptHandler(clause) = handler;
                increments.extend(control_increments(&clause.body, inner));
            }
        }
    }
    increments
}

fn class_fact(source: &Source, module: &ModModule, tokens: &Tokens) -> Value {
    Declared::new(source, module, tokens).fact()
}

/// Every class one file declares, read as the evidence the class rules judge.
///
/// What a class is called, what it derives, what it declares, and what its own constructor does
/// are all in this file. Who imports it, who subclasses it, and who builds one are questions about
/// the whole repository, and the pass that owns the graph answers those over this same fact.
struct Declared<'a> {
    source: &'a Source,
    module: &'a ModModule,
    regions: Vec<usize>,
    exported: Vec<String>,
    bindings: BTreeMap<String, String>,
}

impl<'a> Declared<'a> {
    fn new(source: &'a Source, module: &'a ModModule, tokens: &Tokens) -> Self {
        Self {
            source,
            module,
            regions: region_lines(source, tokens),
            exported: exported_names(module),
            bindings: import_bindings(module),
        }
    }

    /// State every class this file declares, together with what the file itself is.
    fn fact(&self) -> Value {
        let mut classes = Vec::new();
        self.collect(&self.module.body, "module", &mut classes);
        let key = format!("classes:{}", self.source.relative);
        merge(
            base(self.source, &key, self.module.range()),
            json!({
                "classes": classes,
                "projection_groups": self.projections(),
                "model_files": self.model_file(),
                "has_approved_model_foundation_policy": self
                    .bindings
                    .values()
                    .any(|module| is_approved_foundation_module(module)),
            }),
        )
    }

    fn collect(&self, body: &[Stmt], scope: &str, classes: &mut Vec<Value>) {
        for statement in body {
            match statement {
                Stmt::ClassDef(item) => {
                    classes.push(self.class(item, scope));
                    self.collect(&item.body, "nested", classes);
                }
                Stmt::FunctionDef(item) => self.collect(&item.body, "nested", classes),
                _ => {}
            }
        }
    }

    fn class(&self, item: &StmtClassDef, scope: &str) -> Value {
        let name = item.name.to_string();
        let bases = base_names(self.source, item);
        let methods: Vec<Value> = item
            .body
            .iter()
            .filter_map(|member| self.method(item, member))
            .collect();
        let fields = item
            .body
            .iter()
            .filter(|member| matches!(member, Stmt::AnnAssign(_) | Stmt::Assign(_)))
            .count();
        json!({
            "name": name,
            "path": self.source.relative.clone(),
            "span": self.source.span(item.range()),
            "scope": scope,
            "visibility": visibility(&name, scope),
            "direct_bases": item
                .arguments
                .as_ref()
                .map(|arguments| arguments
                    .args
                    .iter()
                    .map(|argument| self.source.slice(argument.range()).to_string())
                    .collect::<Vec<_>>())
                .unwrap_or_default(),
            "class_keywords": item
                .arguments
                .as_ref()
                .map(|arguments| arguments
                    .keywords
                    .iter()
                    .map(|keyword| self.source.slice(keyword.range()).to_string())
                    .collect::<Vec<_>>())
                .unwrap_or_default(),
            "decorators": decorator_texts(self.source, &item.decorator_list),
            "methods": methods,
            "field_count": fields,
            "has_instance_fields": fields > 0,
            "is_exported": self.exported.contains(&name),
            "has_explicit_registry_name": states_registry_name(&item.body),
            "is_pass_through_layer": self.is_pass_through_layer(item),
            "duplicate_component_alias_count": self.duplicate_component_aliases(item),
            "is_declarative_model": self.is_declarative_model(item, &bases),
            "has_ordinary_behavior": self.has_ordinary_behavior(item),
            // The foundation itself is the one class allowed to derive Pydantic directly, since
            // it is what every other class is being asked to derive instead.
            "directly_inherits_pydantic_base_model": !self.is_foundation_module()
                && bases
                    .iter()
                    .any(|held| held == "BaseModel" && self.resolves(held, "pydantic")),
            "inherits_approved_model_foundation": bases.iter().any(|held| {
                self.bindings
                    .get(held)
                    .is_some_and(|module| is_approved_foundation_module(module))
            }),
        })
    }

    fn method(&self, owner: &StmtClassDef, statement: &Stmt) -> Option<Value> {
        let Stmt::FunctionDef(item) = statement else {
            return None;
        };
        let name = item.name.to_string();
        let decorators = decorator_texts(self.source, &item.decorator_list);
        let named = |wanted: &str| {
            decorators
                .iter()
                .any(|decorator| decorator_name(decorator) == wanted)
        };
        let kind = if name == "__init__" || name == "__new__" {
            "constructor"
        } else if named("property") {
            "property"
        } else if named("staticmethod") {
            "static_method"
        } else if named("classmethod") {
            "class_method"
        } else {
            "method"
        };
        Some(json!({
            "name": name,
            "kind": kind,
            "visibility": visibility(&name, "method"),
            "is_protocol_name": is_protocol_name(&name),
            "decorators": decorators,
            "region": self.region_of(statement),
            "owner_qualified_calls": self.owner_qualified_calls(owner, item),
        }))
    }

    /// Return which independently ordered section of its class one member sits in.
    fn region_of(&self, statement: &Stmt) -> usize {
        let line = self.source.line_of(statement.range().start());
        self.regions.iter().filter(|opened| **opened < line).count()
    }

    /// Return every sibling one method calls through the literal name of the class holding it.
    ///
    /// A call inside a nested function is left out, since a closure can rebind the name, and so is
    /// a method that binds the owner name itself, which is the same shadowing one step earlier.
    fn owner_qualified_calls(&self, owner: &StmtClassDef, item: &StmtFunctionDef) -> Vec<String> {
        let held = executable(&item.body);
        let direct: Vec<&Stmt> = statements(held)
            .into_iter()
            .filter(|statement| !matches!(statement, Stmt::FunctionDef(_)))
            .collect();
        let mut found = Vec::new();
        for statement in &direct {
            if binds(statement, owner.name.as_str()) {
                return Vec::new();
            }
            for expression in expressions(statement) {
                descend(expression, &mut found);
            }
        }
        found
            .into_iter()
            .filter_map(|expression| match expression {
                Expr::Call(call) => Some(qualified_name(&call.func)),
                _ => None,
            })
            .filter(|called| called.starts_with(&format!("{}.", owner.name)))
            .collect()
    }

    /// Whether one class adds a name and a forwarding frame rather than behavior.
    ///
    /// A body of nothing but a docstring is not empty. The class said why it exists, which is the
    /// difference between a layer nobody meant to add and a distinct type somebody named.
    fn is_pass_through_layer(&self, item: &StmtClassDef) -> bool {
        if item.body.iter().all(is_placeholder) {
            return true;
        }
        let held = executable(&item.body);
        !held.is_empty()
            && held.iter().all(|member| match member {
                Stmt::FunctionDef(method) => forwards_to_super(method),
                _ => false,
            })
    }

    /// Count fields one constructor copies off a component the same constructor already retained.
    fn duplicate_component_aliases(&self, item: &StmtClassDef) -> usize {
        item.body
            .iter()
            .filter_map(|member| match member {
                Stmt::FunctionDef(method)
                    if matches!(method.name.as_str(), "__init__" | "model_post_init") =>
                {
                    Some(method)
                }
                _ => None,
            })
            .map(|method| {
                let taken: Vec<&str> = method
                    .parameters
                    .iter()
                    .map(|declared| declared.name().as_str())
                    .collect();
                let stored: Vec<&str> = assignments(&method.body)
                    .into_iter()
                    .filter_map(|(field, value)| match value {
                        Expr::Name(held) if taken.contains(&held.id.as_str()) => {
                            Some((field, held.id.as_str()))
                        }
                        _ => None,
                    })
                    .map(|(_, component)| component)
                    .collect();
                assignments(&method.body)
                    .into_iter()
                    .filter(|(_, value)| match value {
                        Expr::Attribute(read) => matches!(
                            read.value.as_ref(),
                            Expr::Name(held) if stored.contains(&held.id.as_str())
                        ),
                        _ => false,
                    })
                    .count()
            })
            .sum()
    }

    /// Whether one class declares data a library validates rather than behavior it runs.
    fn is_declarative_model(&self, item: &StmtClassDef, bases: &[String]) -> bool {
        bases
            .iter()
            .any(|held| MODEL_FOUNDATIONS.contains(&held.as_str()) || held == "DeclarativeBase")
            || decorator_texts(self.source, &item.decorator_list)
                .iter()
                .any(|decorator| decorator_name(decorator) == "dataclass")
    }

    /// Whether one class declares a method a model library would not have called for it.
    fn has_ordinary_behavior(&self, item: &StmtClassDef) -> bool {
        item.body.iter().any(|member| match member {
            Stmt::FunctionDef(method) => {
                let name = method.name.as_str();
                let decorators = decorator_texts(self.source, &method.decorator_list);
                !is_protocol_name(name)
                    && name != "model_post_init"
                    && !decorators.iter().any(|decorator| {
                        matches!(
                            decorator_name(decorator),
                            "cached_property"
                                | "computed_field"
                                | "field_serializer"
                                | "field_validator"
                                | "model_serializer"
                                | "model_validator"
                                | "property"
                                | "root_validator"
                                | "validator"
                        )
                    })
            }
            _ => false,
        })
    }

    /// Whether this file is where the project keeps the model foundation it approved.
    fn is_foundation_module(&self) -> bool {
        let named = self.source.relative.rsplit('/').next().unwrap_or_default();
        named == "bases.py" || named == "bases.pyi"
    }

    /// Whether one name this file binds came from one module.
    fn resolves(&self, name: &str, module: &str) -> bool {
        self.bindings
            .get(name)
            .is_some_and(|origin| origin == module || origin.starts_with(&format!("{module}.")))
    }

    /// Return this file as an entry of a shared models package, when it sits inside one.
    fn model_file(&self) -> Vec<Value> {
        let relative = &self.source.relative;
        if !relative
            .split('/')
            .rev()
            .skip(1)
            .any(|part| part == "models")
        {
            return Vec::new();
        }
        let declared: Vec<&Stmt> = self
            .module
            .body
            .iter()
            .filter(|statement| matches!(statement, Stmt::ClassDef(_)))
            .collect();
        let models = declared
            .iter()
            .filter_map(|statement| match statement {
                Stmt::ClassDef(item) => Some(item),
                _ => None,
            })
            .filter(|item| self.is_declarative_model(item, &base_names(self.source, item)))
            .count();
        vec![json!({
            "path": relative,
            "top_level_class_count": declared.len(),
            "model_class_count": models,
            "is_package_initializer": relative.ends_with("__init__.py"),
        })]
    }

    /// Return every structure in this file that repeats the fields of one object it reads.
    fn projections(&self) -> Vec<Value> {
        let mut found = Vec::new();
        let mut held = Vec::new();
        for statement in walk(self.module) {
            for expression in expressions(statement) {
                descend(expression, &mut held);
            }
        }
        for expression in held {
            let (keys, reads) = match expression {
                Expr::Dict(item) => (
                    item.items
                        .iter()
                        .filter_map(|entry| entry.key.as_ref().and_then(literal_text))
                        .collect::<Vec<_>>(),
                    item.items.iter().map(|entry| &entry.value).collect(),
                ),
                Expr::Call(item) => (
                    item.arguments
                        .keywords
                        .iter()
                        .filter_map(|keyword| keyword.arg.as_ref().map(ToString::to_string))
                        .collect(),
                    item.arguments
                        .keywords
                        .iter()
                        .map(|keyword| &keyword.value)
                        .collect::<Vec<_>>(),
                ),
                Expr::Tuple(item) => pairs(&item.elts),
                Expr::List(item) => pairs(&item.elts),
                _ => continue,
            };
            found.extend(projection_groups(&keys, &reads));
        }
        found
    }
}

/// Return the key and value of every pair a sequence of two element tuples states.
fn pairs(elements: &[Expr]) -> (Vec<String>, Vec<&Expr>) {
    let held: Vec<(String, &Expr)> = elements
        .iter()
        .filter_map(|element| match element {
            Expr::Tuple(pair) => match pair.elts.as_slice() {
                [key, value] => literal_text(key).map(|named| (named, value)),
                _ => None,
            },
            _ => None,
        })
        .collect();
    (
        held.iter().map(|(named, _)| named.clone()).collect(),
        held.into_iter().map(|(_, value)| value).collect(),
    )
}

/// Group the attribute reads of one structure by the object each one starts from.
fn projection_groups(keys: &[String], reads: &[&Expr]) -> Vec<Value> {
    let mut roots: BTreeMap<&str, Vec<String>> = BTreeMap::new();
    for read in reads {
        if let Expr::Attribute(item) = read
            && let Expr::Name(held) = item.value.as_ref()
        {
            roots
                .entry(held.id.as_str())
                .or_default()
                .push(item.attr.to_string());
        }
    }
    roots
        .into_iter()
        .map(|(root, attributes)| {
            json!({"root": root, "attribute_names": attributes, "output_keys": keys})
        })
        .collect()
}

/// Return what one literal says, when the expression is a literal a key can be written as.
fn literal_text(expression: &Expr) -> Option<String> {
    match expression {
        Expr::StringLiteral(literal) => Some(literal.value.to_str().to_string()),
        _ => None,
    }
}

/// Return the line each `# region` marker opens a new independently ordered section on.
fn region_lines(source: &Source, tokens: &Tokens) -> Vec<usize> {
    tokens
        .iter()
        .filter(|token| token.kind() == TokenKind::Comment)
        .filter(|token| {
            comment_body(source.slice(token.range()))
                .trim_start_matches('#')
                .trim_start()
                .to_ascii_lowercase()
                .starts_with("region")
        })
        .map(|token| source.line_of(token.range().start()))
        .collect()
}

/// Return what module each name one file imports came from.
fn import_bindings(module: &ModModule) -> BTreeMap<String, String> {
    let mut bound = BTreeMap::new();
    for statement in walk(module) {
        match statement {
            Stmt::Import(item) => {
                for alias in &item.names {
                    let imported = alias.name.to_string();
                    let name = alias
                        .asname
                        .as_ref()
                        .map(ToString::to_string)
                        .unwrap_or_else(|| imported.clone());
                    bound.insert(name, imported);
                }
            }
            Stmt::ImportFrom(item) => {
                let origin = item
                    .module
                    .as_ref()
                    .map(ToString::to_string)
                    .unwrap_or_default();
                for alias in &item.names {
                    let name = alias
                        .asname
                        .as_ref()
                        .map(ToString::to_string)
                        .unwrap_or_else(|| alias.name.to_string());
                    bound.insert(name, origin.clone());
                }
            }
            _ => {}
        }
    }
    bound
}

/// Whether one module is where this project keeps the model foundation it approved.
fn is_approved_foundation_module(module: &str) -> bool {
    let root = module.split('.').next().unwrap_or(module);
    root == "patos" || module == "common.bases" || module.ends_with(".common.bases")
}

/// Whether one class body assigns the registry key its own name already derives.
fn states_registry_name(body: &[Stmt]) -> bool {
    body.iter().any(|member| match member {
        Stmt::Assign(item) => {
            item.targets
                .iter()
                .any(|target| matches!(target, Expr::Name(held) if held.id.as_str() == "name"))
                && matches!(item.value.as_ref(), Expr::StringLiteral(_))
        }
        Stmt::AnnAssign(item) => {
            matches!(item.target.as_ref(), Expr::Name(held) if held.id.as_str() == "name")
                && matches!(item.value.as_deref(), Some(Expr::StringLiteral(_)))
        }
        _ => false,
    })
}

/// Whether one statement stands in for a body rather than being one.
fn is_placeholder(statement: &Stmt) -> bool {
    match statement {
        Stmt::Pass(_) => true,
        Stmt::Expr(item) => matches!(item.value.as_ref(), Expr::EllipsisLiteral(_)),
        _ => false,
    }
}

/// Whether one statement binds one name, which is what lets a body shadow the class holding it.
fn binds(statement: &Stmt, name: &str) -> bool {
    let targets: Vec<&Expr> = match statement {
        Stmt::Assign(item) => item.targets.iter().collect(),
        Stmt::AnnAssign(item) => vec![item.target.as_ref()],
        Stmt::For(item) => vec![item.target.as_ref()],
        _ => return false,
    };
    targets
        .into_iter()
        .any(|target| matches!(target, Expr::Name(held) if held.id.as_str() == name))
}

/// Return every field one body stores on its receiver, with the expression it stored.
fn assignments(body: &[Stmt]) -> Vec<(String, &Expr)> {
    statements(body)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::Assign(item) => match item.targets.as_slice() {
                [Expr::Attribute(field)] => Some((field, item.value.as_ref())),
                _ => None,
            },
            Stmt::AnnAssign(item) => match (item.target.as_ref(), item.value.as_deref()) {
                (Expr::Attribute(field), Some(value)) => Some((field, value)),
                _ => None,
            },
            _ => None,
        })
        .filter(|(field, _)| matches!(field.value.as_ref(), Expr::Name(held) if held.id == "self"))
        .map(|(field, value)| (field.attr.to_string(), value))
        .collect()
}

/// Whether one method hands every argument it was given straight to the same method above it.
fn forwards_to_super(item: &StmtFunctionDef) -> bool {
    let [Stmt::Return(returned)] = executable(&item.body) else {
        return false;
    };
    let Some(Expr::Call(call)) = returned.value.as_deref() else {
        return false;
    };
    let Expr::Attribute(member) = call.func.as_ref() else {
        return false;
    };
    let Expr::Call(receiver) = member.value.as_ref() else {
        return false;
    };
    member.attr.as_str() == item.name.as_str()
        && qualified_name(&receiver.func) == "super"
        && receiver.arguments.args.is_empty()
        && passes_through(&item.parameters, &call.arguments)
}

/// Whether one call restates exactly the parameters one signature declares, in their own order.
fn passes_through(declared: &Parameters, arguments: &ruff_python_ast::Arguments) -> bool {
    let mut expected: Vec<String> = declared
        .posonlyargs
        .iter()
        .chain(declared.args.iter())
        .map(|parameter| parameter.parameter.name.to_string())
        .skip(1)
        .collect();
    expected.extend(
        declared
            .vararg
            .as_ref()
            .map(|parameter| format!("*{}", parameter.name)),
    );
    let mut passed: Vec<String> = arguments
        .args
        .iter()
        .map(|argument| match argument {
            Expr::Name(held) => held.id.to_string(),
            Expr::Starred(held) => format!("*{}", root_name(&held.value)),
            _ => String::new(),
        })
        .collect();
    let mut named: Vec<String> = declared
        .kwonlyargs
        .iter()
        .map(|parameter| parameter.parameter.name.to_string())
        .collect();
    named.extend(
        declared
            .kwarg
            .as_ref()
            .map(|parameter| format!("**{}", parameter.name)),
    );
    let mut given: Vec<String> = arguments
        .keywords
        .iter()
        .map(|keyword| match (&keyword.arg, &keyword.value) {
            (Some(name), Expr::Name(held)) if held.id.as_str() == name.as_str() => {
                name.to_string()
            }
            (None, value) => format!("**{}", root_name(value)),
            _ => String::new(),
        })
        .collect();
    named.sort();
    given.sort();
    expected.sort();
    passed.sort();
    expected == passed && named == given
}

/// One run of comment lines that sit directly above one another.
#[derive(Default)]
struct CommentGroup {
    last_line: usize,
    line_count: usize,
    character_count: usize,
    token_count: usize,
    body: String,
    is_directive: bool,
    range: ruff_text_size::TextRange,
}

impl CommentGroup {
    fn start(line: usize, text: &str, range: ruff_text_size::TextRange) -> Self {
        let mut group = Self {
            last_line: line,
            is_directive: is_directive(text),
            range,
            ..Self::default()
        };
        group.absorb(line, text, range);
        group
    }

    fn absorb(&mut self, line: usize, text: &str, range: ruff_text_size::TextRange) {
        self.range = ruff_text_size::TextRange::new(self.range.start(), range.end());
        self.last_line = line;
        self.line_count += 1;
        self.character_count += text.len();
        self.token_count += text.split_whitespace().count();
        if !self.body.is_empty() {
            self.body.push('\n');
        }
        self.body.push_str(comment_body(text));
    }

    fn value(&self, source: &Source) -> Value {
        json!({
            "line_count": self.line_count,
            "character_count": self.character_count,
            "token_count": self.token_count,
            "parses_as_source": !self.is_directive && parses_as_statement(self.body.trim()),
            "is_directive": self.is_directive,
            "node": source.node("comment", self.range),
        })
    }
}

fn comment_fact(source: &Source, tokens: &Tokens) -> Value {
    let mut groups: Vec<Value> = Vec::new();
    let mut current: Option<CommentGroup> = None;
    for token in tokens
        .iter()
        .filter(|token| token.kind() == TokenKind::Comment)
    {
        let text = source.slice(token.range());
        let line = source.line_of(token.range().start());
        match current.as_mut() {
            Some(group)
                if group.last_line + 1 == line && group.is_directive == is_directive(text) =>
            {
                group.absorb(line, text, token.range());
            }
            _ => {
                let started = CommentGroup::start(line, text, token.range());
                if let Some(group) = current.replace(started) {
                    groups.push(group.value(source));
                }
            }
        }
    }
    if let Some(group) = current {
        groups.push(group.value(source));
    }
    let key = format!("comments:{}", source.relative);
    merge(
        base(source, &key, ruff_text_size::TextRange::default()),
        json!({"groups": groups}),
    )
}

/// Return what one comment line says, without the marker that made it a comment.
///
/// Only the marker and the single space after it are removed. A commented-out block is recognized
/// by parsing what it says, and a block whose indentation was trimmed away cannot parse, so the
/// one rule that finds commented-out code depends on keeping the shape of the lines intact.
fn comment_body(text: &str) -> &str {
    let body = text.trim_start_matches('#');
    body.strip_prefix(' ').unwrap_or(body).trim_end()
}

fn is_directive(text: &str) -> bool {
    let body = comment_body(text).to_ascii_lowercase();
    [
        "noqa", "type:", "pragma", "ruff:", "mypy:", "pyright:", "fmt:", "isort:",
    ]
    .iter()
    .any(|marker| body.starts_with(marker))
}

/// Whether one comment body is source rather than prose, decided by parsing it.
fn parses_as_statement(text: &str) -> bool {
    !text.is_empty() && text.contains(['=', '(', ':']) && parse_module(text).is_ok()
}

fn call_fact(source: &Source, module: &ModModule) -> Value {
    let mut calls = Vec::new();
    collect_calls(source, &module.body, &mut calls);
    let bindings: Vec<String> = module.body.iter().filter_map(declared_name).collect();
    let key = format!("calls:{}", source.relative);
    merge(
        base(source, &key, module.range()),
        json!({"calls": calls, "module_bindings": bindings}),
    )
}

fn collect_calls(source: &Source, body: &[Stmt], calls: &mut Vec<Value>) {
    for statement in body {
        let discarded = matches!(statement, Stmt::Expr(_));
        for expression in expressions(statement) {
            collect_call_expressions(source, expression, discarded, calls);
        }
        for block in blocks(statement) {
            collect_calls(source, block, calls);
        }
    }
}

fn collect_call_expressions(
    source: &Source,
    expression: &Expr,
    discarded: bool,
    calls: &mut Vec<Value>,
) {
    if let Expr::Call(item) = expression {
        calls.push(json!({
            "qualified_name": qualified_name(&item.func),
            "path": source.relative.clone(),
            "arguments": item
                .arguments
                .args
                .iter()
                .map(|argument| argument_value(source, argument))
                .collect::<Vec<_>>(),
            "keyword_names": item
                .arguments
                .keywords
                .iter()
                .filter_map(|keyword| keyword.arg.as_ref().map(ToString::to_string))
                .collect::<Vec<_>>(),
            "receiver": receiver(source, &item.func),
            "result_is_discarded": discarded,
            "node": source.node_of("call", item),
            "callee": source.node_of("callee", item.func.as_ref()),
        }));
    }
    for child in children(expression) {
        collect_call_expressions(source, child, false, calls);
    }
}

fn argument_value(source: &Source, expression: &Expr) -> Value {
    json!({
        "text": source.slice(expression.range()),
        "qualified_name": match expression {
            Expr::Call(call) => qualified_name(&call.func),
            _ => String::new(),
        },
        "literal_kind": literal_kind(expression),
        "arguments": match expression {
            Expr::Call(call) => call
                .arguments
                .args
                .iter()
                .map(|argument| argument_value(source, argument))
                .collect::<Vec<_>>(),
            _ => Vec::new(),
        },
        "entries": match expression {
            Expr::Dict(dict) => dict
                .items
                .iter()
                .filter_map(|item| item.key.as_ref().map(|key| json!({
                    "key": source.slice(key.range()).trim_matches(['"', '\'']),
                    "value": {"text": source.slice(item.value.range())},
                })))
                .collect::<Vec<_>>(),
            _ => Vec::new(),
        },
        "node": source.node_of("expression", expression),
    })
}

fn literal_kind(expression: &Expr) -> &'static str {
    match expression {
        Expr::StringLiteral(_) => "string",
        Expr::NumberLiteral(_) => "number",
        Expr::BooleanLiteral(_) => "boolean",
        Expr::Dict(_) => "mapping",
        Expr::List(_) | Expr::Tuple(_) | Expr::Set(_) => "sequence",
        _ => "none",
    }
}

fn receiver(source: &Source, callee: &Expr) -> Value {
    match callee {
        Expr::Attribute(attribute) => json!({
            "text": source.slice(attribute.value.range()),
            "qualified_name": qualified_name(&attribute.value),
        }),
        _ => Value::Null,
    }
}

/// Every name one module reads, counted where the interpreter would read it.
///
/// A resolver that misses one position invents an unused import out of live code, and the
/// positions that were missed were never exotic. A name tested by an `elif`, named as the type an
/// `except` catches, or matched by a `case` are all ordinary Python that a hand-written list of
/// interesting expressions simply did not reach. Riding the parser's own traversal is what keeps
/// that list from being written again, and the day the language grows a position the traversal
/// grows with it.
///
/// Reading a name and mentioning it are counted apart, because they answer different questions. A
/// forward reference written inside a string and a later binding of the same name both mean that
/// deleting the import is not the repair, while neither says the module treats the name as a
/// value, which is the only thing a first-class reference is about.
#[derive(Default)]
struct ReferenceIndex {
    loads: BTreeMap<String, usize>,
    mentions: BTreeMap<String, usize>,
    typed: usize,
}

impl ReferenceIndex {
    fn of(module: &ModModule) -> Self {
        let mut index = Self::default();
        index.visit_body(&module.body);
        index
    }

    /// Return how many times one name is read or otherwise mentioned outside its own import.
    fn reads(&self, name: &str) -> usize {
        self.loads.get(name).copied().unwrap_or_default()
            + self.mentions.get(name).copied().unwrap_or_default()
    }

    /// Read one expression as a type expression or as ordinary code, whichever it is.
    fn read(&mut self, expression: &Expr, as_type: bool) {
        let outer = self.typed;
        self.typed = if as_type { outer + 1 } else { 0 };
        self.visit_expr(expression);
        self.typed = outer;
    }

    /// Read the arguments of one typing constructor, which state types written as text.
    ///
    /// `cast` takes its type first and the rest take a name first, and reading a name string as a
    /// type expression only ever counts the name a declaration is giving itself, so all of them
    /// are read the same way rather than each being given its own argument positions.
    fn constructor(&mut self, item: &ruff_python_ast::ExprCall) {
        self.visit_expr(&item.func);
        for argument in &item.arguments.args {
            self.read(argument, true);
        }
        for keyword in &item.arguments.keywords {
            self.read(&keyword.value, true);
        }
    }

    /// Read the slice of one subscript, which is a type expression unless the base says otherwise.
    ///
    /// `Literal` states values rather than types, and only the first argument of `Annotated` is
    /// the type it qualifies, so a string under either of those is text rather than a name.
    fn subscript(&mut self, item: &ruff_python_ast::ExprSubscript) {
        self.visit_expr(&item.value);
        let base = qualified_name(&item.value);
        match base.rsplit('.').next().unwrap_or_default() {
            "Literal" => self.read(&item.slice, false),
            "Annotated" => match item.slice.as_ref() {
                Expr::Tuple(tuple) => tuple
                    .elts
                    .iter()
                    .enumerate()
                    .for_each(|(position, element)| self.read(element, position == 0)),
                slice => self.read(slice, true),
            },
            _ => self.read(&item.slice, true),
        }
    }

    /// Count the names one string spells, which is how a forward reference is written.
    ///
    /// The string is parsed rather than scanned, so text that is not an expression contributes
    /// nothing and a nested reference contributes what it names.
    fn forward_reference(&mut self, text: &str) {
        let Ok(parsed) = ruff_python_parser::parse_expression(text) else {
            return;
        };
        let mut inner = Self {
            typed: 1,
            ..Self::default()
        };
        inner.visit_expr(&parsed.syntax().body);
        for (name, count) in inner.loads.into_iter().chain(inner.mentions) {
            *self.mentions.entry(name).or_default() += count;
        }
    }
}

impl<'a> Visitor<'a> for ReferenceIndex {
    fn visit_stmt(&mut self, statement: &'a Stmt) {
        match statement {
            Stmt::TypeAlias(item) => {
                self.read(&item.value, true);
                if let Some(parameters) = &item.type_params {
                    self.visit_type_params(parameters);
                }
            }
            // The traversal hands an `elif` test to a visitor twice, once from the statement
            // holding the clause and once from the clause itself, so taking the default would
            // report one test as two reads and turn a called name into a first-class reference.
            Stmt::If(item) => {
                self.visit_expr(&item.test);
                self.visit_body(&item.body);
                for clause in &item.elif_else_clauses {
                    if let Some(test) = &clause.test {
                        self.visit_expr(test);
                    }
                    self.visit_body(&clause.body);
                }
            }
            _ => visitor::walk_stmt(self, statement),
        }
    }

    fn visit_annotation(&mut self, expression: &'a Expr) {
        self.read(expression, true);
    }

    fn visit_expr(&mut self, expression: &'a Expr) {
        match expression {
            // A delete needs the binding to exist, so it reads it. A store replaces it, which is
            // the shape a type-only import with a runtime placeholder takes, and deleting the
            // import there breaks the type checker rather than repairing anything.
            Expr::Name(name) if matches!(name.ctx, ExprContext::Load | ExprContext::Del) => {
                *self.loads.entry(name.id.to_string()).or_default() += 1;
            }
            Expr::Name(name) => *self.mentions.entry(name.id.to_string()).or_default() += 1,
            Expr::StringLiteral(literal) if self.typed > 0 => {
                self.forward_reference(literal.value.to_str());
            }
            Expr::Subscript(item) => return self.subscript(item),
            Expr::Call(item) if states_types(&item.func) => return self.constructor(item),
            _ => {}
        }
        visitor::walk_expr(self, expression);
    }
}

/// Whether one callee is a typing constructor stating a type where a traversal reads ordinary code.
///
/// Every entry is named in the typing specification, which is what keeps this a closed vocabulary
/// rather than a list that grows with taste. Without it a forward reference handed to `cast` or
/// listed as a `TypeVar` constraint is text, and the import it names reads as dead.
fn states_types(callee: &Expr) -> bool {
    matches!(
        qualified_name(callee)
            .rsplit('.')
            .next()
            .unwrap_or_default(),
        "cast"
            | "NamedTuple"
            | "NewType"
            | "ParamSpec"
            | "TypeAliasType"
            | "TypeVar"
            | "TypeVarTuple"
            | "TypedDict"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn facts_for(source: &str, family: &str) -> Vec<Value> {
        let document = Document {
            relative: "example.py".to_string(),
            source: source.to_string(),
        };
        let mut facts = BTreeMap::from([(family.to_string(), Vec::new())]);
        let mut stats = Stats::default();
        extract(
            &document,
            &crate::discovery::Packages::default(),
            &mut facts,
            &mut stats,
        );
        facts.remove(family).unwrap_or_default()
    }

    #[test]
    fn import_bindings_carry_their_references_and_origin() {
        let facts = facts_for(
            "import json\nfrom . import models\nprint(json.dumps(1))\n",
            "ImportBindingFact",
        );
        assert_eq!(facts.len(), 2);
        assert_eq!(facts[0]["name"], "json");
        assert_eq!(facts[0]["reference_count"], 1);
        assert_eq!(facts[0]["is_relative"], false);
        assert_eq!(facts[1]["name"], "models");
        assert_eq!(facts[1]["reference_count"], 0);
        assert_eq!(facts[1]["is_relative"], true);
        assert_eq!(facts[1]["is_sole_binding"], true);
    }

    fn binding_named(source: &str, name: &str) -> Value {
        facts_for(source, "ImportBindingFact")
            .into_iter()
            .find(|fact| fact["name"] == name)
            .expect("the name is bound by an import")
    }

    #[test]
    fn a_name_is_read_wherever_the_interpreter_would_read_it() {
        let source = concat!(
            "import json\n",
            "import math\n",
            "import re\n",
            "import textwrap\n",
            "import unicodedata\n\n\n",
            "def run(value):\n",
            "    if value == 1:\n",
            "        return 0\n",
            "    elif isinstance(value, json.JSONDecoder):\n",
            "        return 1\n",
            "    try:\n",
            "        del textwrap.cache\n",
            "    except math.error as failure:\n",
            "        raise unicodedata.UnicodeError from failure\n",
            "    match value:\n",
            "        case re.Match():\n",
            "            return 3\n",
            "    return 4\n",
        );

        for name in ["json", "math", "re", "textwrap", "unicodedata"] {
            assert_eq!(binding_named(source, name)["reference_count"], 1, "{name}");
        }
    }

    #[test]
    fn a_forward_reference_written_as_a_string_reads_the_name_it_spells() {
        let source = concat!(
            "from typing import Annotated, Literal, Optional\n",
            "from decimal import Decimal\n",
            "from fractions import Fraction\n",
            "from numbers import Number\n",
            "from pathlib import Path\n",
            "from uuid import UUID\n\n",
            "Alias = Optional[\"Decimal\"]\n",
            "Deep = dict[str, \"Fraction\"]\n",
            "Valued = Literal[\"Number\"]\n",
            "Tagged = Annotated[int, \"Path\"]\n",
            "type Money = \"UUID\"\n",
        );

        assert_eq!(binding_named(source, "Decimal")["reference_count"], 1);
        assert_eq!(binding_named(source, "Fraction")["reference_count"], 1);
        assert_eq!(binding_named(source, "UUID")["reference_count"], 1);
        assert_eq!(binding_named(source, "Number")["reference_count"], 0);
        assert_eq!(binding_named(source, "Path")["reference_count"], 0);
    }

    #[test]
    fn a_typing_constructor_states_its_types_as_text_and_they_are_read_as_types() {
        let source = concat!(
            "from typing import TypeVar, cast\n",
            "from decimal import Decimal\n",
            "from fractions import Fraction\n",
            "from uuid import UUID\n\n",
            "Number = TypeVar(\"Number\", int, \"Decimal\")\n",
            "def run(value):\n",
            "    return cast(\"list[Fraction]\", value)\n",
            "def carry(value):\n",
            "    return str(\"UUID\")\n",
        );

        assert_eq!(binding_named(source, "Decimal")["reference_count"], 1);
        assert_eq!(binding_named(source, "Fraction")["reference_count"], 1);
        assert_eq!(binding_named(source, "UUID")["reference_count"], 0);
    }

    #[test]
    fn a_name_the_module_binds_again_is_one_no_deletion_repairs() {
        let source = concat!(
            "from typing import TYPE_CHECKING\n",
            "if TYPE_CHECKING:\n",
            "    from decimal import Decimal\n",
            "else:\n",
            "    Decimal = None\n",
            "from fractions import Fraction\n",
        );

        assert_eq!(binding_named(source, "Decimal")["reference_count"], 1);
        assert_eq!(binding_named(source, "Decimal")["has_qualifying_use"], true);
        assert_eq!(binding_named(source, "Fraction")["reference_count"], 0);
    }

    #[test]
    fn an_import_under_a_failure_guard_is_there_for_whether_it_succeeds() {
        let source = concat!(
            "try:\n",
            "    import h2\n",
            "except ImportError:\n",
            "    import tomli\n",
            "try:\n",
            "    import socksio\n",
            "except ValueError:\n",
            "    pass\n",
        );

        assert_eq!(
            binding_named(source, "h2")["has_documented_side_effect"],
            true
        );
        assert_eq!(
            binding_named(source, "tomli")["has_documented_side_effect"],
            false
        );
        assert_eq!(
            binding_named(source, "socksio")["has_documented_side_effect"],
            false
        );
    }

    #[test]
    fn a_statement_binding_several_names_is_not_one_a_deletion_repairs() {
        let source = "from json import dumps, loads\nimport math\n";

        assert_eq!(binding_named(source, "dumps")["is_sole_binding"], false);
        assert_eq!(binding_named(source, "loads")["is_sole_binding"], false);
        assert_eq!(binding_named(source, "math")["is_sole_binding"], true);
    }

    #[test]
    fn a_public_surface_is_read_however_the_module_builds_it() {
        let source = concat!(
            "from .api import Client\n",
            "from .engine import Engine\n",
            "from .errors import Failure\n",
            "from .ports import Port\n",
            "__all__ = [\"Client\"]\n",
            "__all__ += [\"Engine\"]\n",
            "if True:\n",
            "    __all__ = [*__all__, \"Failure\"]\n",
        );

        for name in ["Client", "Engine", "Failure"] {
            assert_eq!(binding_named(source, name)["is_reexported"], true, "{name}");
        }
        assert_eq!(binding_named(source, "Port")["is_reexported"], false);
    }

    fn function_named(source: &str, name: &str) -> Value {
        facts_for(source, "FunctionFact")
            .into_iter()
            .find(|fact| fact["name"] == name)
            .expect("the callable is declared")
    }

    #[test]
    fn implementation_lines_leave_documentation_comments_and_blanks_out() {
        let source = concat!(
            "def read(value):\n",
            "    \"\"\"Explain this callable across\n",
            "    several lines without making it longer.\n",
            "    \"\"\"\n",
            "    prepared = value.strip()\n",
            "\n",
            "    # The explanation between statements is not work either.\n",
            "    return prepared\n",
        );

        assert_eq!(function_named(source, "read")["implementation_lines"], 2);
    }

    #[test]
    fn a_decorator_says_what_binds_a_member_and_who_calls_it() {
        let source = concat!(
            "import functools\n",
            "from typing import overload, override\n\n\n",
            "class Engine(Protocol):\n",
            "    @property\n",
            "    def size(self):\n",
            "        return 1\n\n",
            "    @functools.cache\n",
            "    def parse(self, text):\n",
            "        return text\n\n",
            "    @overload\n",
            "    def read(self, first): ...\n\n",
            "    @override\n",
            "    def run(self):\n",
            "        return 2\n\n",
            "    @app.route(\"/health\")\n",
            "    def health(self):\n",
            "        return 3\n",
        );

        assert_eq!(function_named(source, "size")["is_property"], true);
        assert_eq!(function_named(source, "size")["cache_decorator"], "");
        assert_eq!(function_named(source, "parse")["cache_decorator"], "cache");
        assert_eq!(function_named(source, "parse")["is_property"], false);
        assert_eq!(function_named(source, "read")["is_overload"], true);
        assert_eq!(function_named(source, "run")["is_polymorphic"], true);
        assert_eq!(function_named(source, "run")["is_framework_hook"], false);
        assert_eq!(function_named(source, "health")["is_framework_hook"], true);
        assert_eq!(function_named(source, "size")["is_protocol_member"], true);
    }

    #[test]
    fn a_body_states_what_it_reads_calls_and_hands_back() {
        let source = concat!(
            "def normalize(value):\n",
            "    return underscore(value)\n\n\n",
            "def walk(node):\n",
            "    return walk(node.parent)\n\n\n",
            "class Client:\n",
            "    def size(self):\n",
            "        return len(self.rows)\n\n",
            "    def build(self):\n",
            "        return Client()\n",
        );

        assert_eq!(
            function_named(source, "normalize")["returns_single_call"],
            true
        );
        assert_eq!(
            function_named(source, "normalize")["forwards_only_parameter_unchanged"],
            true
        );
        assert_eq!(
            function_named(source, "normalize")["behavior_operation_count"],
            1
        );
        assert_eq!(function_named(source, "walk")["is_recursive"], true);
        assert_eq!(
            function_named(source, "walk")["forwards_only_parameter_unchanged"],
            false
        );
        assert_eq!(function_named(source, "size")["reads_receiver"], true);
        assert_eq!(function_named(source, "build")["reads_receiver"], false);
    }

    #[test]
    fn a_helper_one_method_calls_names_the_class_that_owns_it() {
        let source = concat!(
            "def parse(text):\n",
            "    return text.strip()\n\n\n",
            "def widen(text):\n",
            "    return text.upper()\n\n\n",
            "class Client:\n",
            "    def read(self, text):\n",
            "        return parse(text)\n\n\n",
            "handler = widen\n",
        );

        assert_eq!(
            function_named(source, "parse")["sole_reference_owner_class"],
            "Client"
        );
        assert_eq!(
            function_named(source, "parse")["is_first_class_reference"],
            false
        );
        assert_eq!(
            function_named(source, "widen")["sole_reference_owner_class"],
            ""
        );
        assert_eq!(
            function_named(source, "widen")["is_first_class_reference"],
            true
        );
    }

    #[test]
    fn a_factory_reproducing_field_validation_states_all_three_halves_of_that() {
        let source = concat!(
            "class Order(BaseModel):\n",
            "    @classmethod\n",
            "    def from_table(cls, rows):\n",
            "        if not isinstance(rows, list):\n",
            "            raise ValueError(rows)\n",
            "        return cls(rows=rows)\n\n",
            "    @field_validator(\"rows\")\n",
            "    @classmethod\n",
            "    def check(cls, value):\n",
            "        return value\n",
        );
        let factory = function_named(source, "from_table");

        assert_eq!(factory["is_model_method"], true);
        assert_eq!(factory["is_pydantic_validator"], false);
        assert_eq!(factory["checks_raw_input_type"], true);
        assert_eq!(factory["raises_validation_exception"], true);
        assert_eq!(factory["constructs_owner_model"], true);
        assert_eq!(
            function_named(source, "check")["is_pydantic_validator"],
            true
        );
    }

    #[test]
    fn only_the_asyncio_this_file_imported_counts_as_scheduling_work() {
        let scheduled = concat!(
            "import asyncio\n\n\n",
            "async def run(items):\n",
            "    first = asyncio.create_task(load(items))\n",
            "    second = asyncio.create_task(save(items))\n",
            "    return await asyncio.gather(first, second)\n",
        );
        let named = concat!(
            "def create_task(subject):\n",
            "    return subject\n\n\n",
            "def create_all_tasks():\n",
            "    return [create_task(name) for name in NAMES]\n",
        );

        assert_eq!(function_named(scheduled, "run")["created_task_count"], 2);
        assert_eq!(
            function_named(scheduled, "run")["gather_consumes_created_tasks"],
            true
        );
        assert_eq!(
            function_named(scheduled, "run")["gather_returns_exceptions"],
            false
        );
        assert_eq!(
            function_named(named, "create_all_tasks")["created_task_count"],
            0
        );
    }

    #[test]
    fn a_gather_told_to_hand_failures_back_is_not_a_task_group_candidate() {
        let source = concat!(
            "import asyncio\n\n\n",
            "async def run(items):\n",
            "    async with asyncio.TaskGroup() as group:\n",
            "        held = [asyncio.create_task(load(item)) for item in items]\n",
            "    return await asyncio.gather(*held, return_exceptions=True)\n",
        );
        let found = function_named(source, "run");

        assert_eq!(found["has_task_group"], true);
        assert_eq!(found["gather_returns_exceptions"], true);
    }

    #[test]
    fn a_tensor_signature_states_its_roles_and_what_the_docstring_settled() {
        let bare = concat!(
            "def normalize(values: torch.Tensor) -> torch.Tensor:\n",
            "    \"\"\"Normalize values.\"\"\"\n",
            "    return values\n",
        );
        let told = concat!(
            "def normalize(values: torch.Tensor) -> torch.Tensor:\n",
            "    \"\"\"Normalize a float32 tensor with shape [batch, features].\"\"\"\n",
            "    return values\n",
        );
        let typed = concat!(
            "def scale(values: Float32[Tensor, \"batch features\"]) -> int:\n",
            "    return 1\n",
        );

        assert_eq!(
            function_named(bare, "normalize")["recognized_tensor_roles"],
            json!(["values", "return"])
        );
        assert_eq!(
            function_named(bare, "normalize")["has_tensor_shape_semantics"],
            false
        );
        assert_eq!(
            function_named(told, "normalize")["has_tensor_shape_semantics"],
            true
        );
        assert_eq!(
            function_named(told, "normalize")["has_tensor_dtype_semantics"],
            true
        );
        assert_eq!(
            function_named(typed, "scale")["has_tensor_shape_semantics"],
            true
        );
        assert_eq!(
            function_named(typed, "scale")["has_tensor_dtype_semantics"],
            true
        );
    }

    #[test]
    fn a_default_says_whether_a_caller_reads_a_flag_at_the_call_site() {
        let facts = facts_for(
            "def render(document, inline=True, width=80):\n    return 1\n",
            "FunctionFact",
        );
        let parameters = facts[0]["parameters"].as_array().expect("a list");

        assert_eq!(parameters[1]["has_boolean_default"], true);
        assert_eq!(parameters[2]["has_boolean_default"], false);
    }

    #[test]
    fn a_class_states_its_keywords_its_registry_key_and_the_regions_it_holds() {
        let source = concat!(
            "class Engine(Base, metaclass=Meta):\n",
            "    name = \"engine\"\n\n",
            "    def open(self):\n",
            "        return 1\n\n",
            "    # region reading\n",
            "    def read(self):\n",
            "        return 2\n",
        );
        let held = &facts_for(source, "ClassFact")[0]["classes"][0];

        assert_eq!(held["class_keywords"], json!(["metaclass=Meta"]));
        assert_eq!(held["has_explicit_registry_name"], true);
        assert_eq!(held["methods"][0]["region"], 0);
        assert_eq!(held["methods"][1]["region"], 1);
        assert_eq!(held["span"]["start_line"], 1);
        assert_eq!(held["span"]["end_line"], 9);
    }

    #[test]
    fn a_layer_adding_only_a_name_or_a_forwarding_frame_states_that_it_passes_through() {
        let empty = facts_for("class Json(Serializer):\n    pass\n", "ClassFact");
        let forwarding = facts_for(
            "class Named(Parser):\n    def parse(self, text, *rest, strict=False):\n        return super().parse(text, *rest, strict=strict)\n",
            "ClassFact",
        );
        let real = facts_for(
            "class Json(Serializer):\n    def encode(self, value):\n        return dumps(value)\n",
            "ClassFact",
        );

        assert_eq!(empty[0]["classes"][0]["is_pass_through_layer"], true);
        assert_eq!(forwarding[0]["classes"][0]["is_pass_through_layer"], true);
        assert_eq!(real[0]["classes"][0]["is_pass_through_layer"], false);
    }

    #[test]
    fn a_field_copied_off_a_component_the_owner_already_keeps_is_counted_once() {
        let source = concat!(
            "class Report:\n",
            "    def __init__(self, document, width):\n",
            "        self.document = document\n",
            "        self.path = document.path\n",
            "        self.title = normalize(document.title)\n",
            "        self.width = width\n",
        );

        assert_eq!(
            facts_for(source, "ClassFact")[0]["classes"][0]["duplicate_component_alias_count"],
            1
        );
    }

    #[test]
    fn a_static_method_calling_a_sibling_through_the_owner_name_states_that_call() {
        let source = concat!(
            "class Parser:\n",
            "    @classmethod\n",
            "    def from_text(cls, text):\n",
            "        return cls()\n\n",
            "    @staticmethod\n",
            "    def decide(text):\n",
            "        return Parser.from_text(text)\n",
        );
        let methods = facts_for(source, "ClassFact")[0]["classes"][0]["methods"].clone();

        assert_eq!(
            methods[1]["owner_qualified_calls"],
            json!(["Parser.from_text"])
        );
        assert_eq!(methods[0]["owner_qualified_calls"], json!([] as [&str; 0]));
    }

    #[test]
    fn a_structure_repeating_the_fields_of_one_object_states_its_keys_beside_them() {
        let source = concat!(
            "def render(definition):\n",
            "    return {\n",
            "        \"id\": definition.id,\n",
            "        \"summary\": definition.summary,\n",
            "        \"scope\": definition.scope,\n",
            "        \"lane\": definition.lane,\n",
            "    }\n",
        );
        let groups = facts_for(source, "ClassFact")[0]["projection_groups"].clone();

        assert_eq!(groups[0]["root"], "definition");
        assert_eq!(
            groups[0]["attribute_names"],
            json!(["id", "summary", "scope", "lane"])
        );
        assert_eq!(
            groups[0]["output_keys"],
            json!(["id", "summary", "scope", "lane"])
        );
    }

    #[test]
    fn control_increments_record_their_nesting_depth() {
        let facts = facts_for(
            "def run(items):\n    for item in items:\n        if item:\n            return item\n",
            "FunctionFact",
        );
        let increments = facts[0]["control_increments"].as_array().unwrap();
        assert_eq!(increments.len(), 2);
        assert_eq!(increments[0]["kind"], "loop");
        assert_eq!(increments[0]["nesting_depth"], 0);
        assert_eq!(increments[1]["kind"], "conditional");
        assert_eq!(increments[1]["nesting_depth"], 1);
    }

    #[test]
    fn classes_carry_members_with_their_kind_and_visibility() {
        let facts = facts_for(
            "class Engine:\n    limit: int = 3\n\n    def __init__(self):\n        pass\n\n    @property\n    def _state(self):\n        return 1\n",
            "ClassFact",
        );
        let classes = facts[0]["classes"].as_array().unwrap();
        assert_eq!(classes[0]["name"], "Engine");
        assert_eq!(classes[0]["field_count"], 1);
        let methods = classes[0]["methods"].as_array().unwrap();
        assert_eq!(methods[0]["kind"], "constructor");
        assert_eq!(methods[1]["kind"], "property");
        assert_eq!(methods[1]["visibility"], "protected");
    }

    #[test]
    fn calls_resolve_their_name_receiver_and_discarded_result() {
        let facts = facts_for(
            "import shutil\nshutil.rmtree(path)\nvalue = len(items)\n",
            "CallFact",
        );
        let calls = facts[0]["calls"].as_array().unwrap();
        assert_eq!(calls[0]["qualified_name"], "shutil.rmtree");
        assert_eq!(calls[0]["result_is_discarded"], true);
        assert_eq!(calls[0]["receiver"]["text"], "shutil");
        assert_eq!(calls[1]["qualified_name"], "len");
        assert_eq!(calls[1]["result_is_discarded"], false);
    }

    #[test]
    fn comment_groups_separate_directives_from_commented_out_code() {
        let facts = facts_for(
            "# noqa: E501\nvalue = 1\n# total = compute(value)\n# print(total)\n\n# a real sentence\n",
            "CommentFact",
        );
        let groups = facts[0]["groups"].as_array().unwrap();
        assert_eq!(groups[0]["is_directive"], true);
        assert_eq!(groups[0]["parses_as_source"], false);
        assert_eq!(groups[1]["line_count"], 2);
        assert_eq!(groups[1]["parses_as_source"], true);
        assert_eq!(groups[2]["line_count"], 1);
        assert_eq!(groups[2]["parses_as_source"], false);
    }

    fn collections_in(body: &str) -> Vec<Value> {
        facts_for(body, "CollectionFact")[0]["local_collections"]
            .as_array()
            .cloned()
            .unwrap_or_default()
    }

    #[test]
    fn a_literal_read_only_by_a_loop_states_that_every_read_iterates() {
        let found = collections_in(
            "def run():\n    formats = (\"json\", \"toml\")\n    for name in formats:\n        print(name)\n",
        );

        assert_eq!(found.len(), 1);
        assert_eq!(found[0]["name"], "formats");
        assert_eq!(found[0]["kind"], "tuple");
        assert_eq!(found[0]["all_reads_are_iteration"], true);
        assert_eq!(found[0]["all_reads_are_membership"], false);
        assert_eq!(found[0]["has_homogeneous_literals"], true);
    }

    #[test]
    fn a_comprehension_iterates_the_same_way_a_loop_statement_does() {
        let found = collections_in(
            "def run():\n    formats = [\"json\", \"toml\"]\n    return [name.upper() for name in formats]\n",
        );

        assert_eq!(found[0]["all_reads_are_iteration"], true);
    }

    #[test]
    fn a_literal_read_only_by_a_membership_test_states_that_and_its_uniqueness() {
        let found = collections_in(
            "def run(value):\n    formats = [\"json\", \"toml\", \"json\"]\n    return value in formats\n",
        );

        assert_eq!(found[0]["all_reads_are_membership"], true);
        assert_eq!(found[0]["all_reads_are_iteration"], false);
        assert_eq!(found[0]["values_are_unique"], false);
    }

    #[test]
    fn one_representation_sensitive_read_leaves_both_claims_false() {
        let found = collections_in(
            "def run():\n    formats = [\"json\", \"toml\"]\n    for name in formats:\n        print(name)\n    return formats[0]\n",
        );

        assert_eq!(found[0]["all_reads_are_iteration"], false);
        assert_eq!(found[0]["all_reads_are_membership"], false);
    }

    #[test]
    fn a_module_constant_and_a_rebound_local_are_not_candidates() {
        assert!(collections_in("FORMATS = [\"json\", \"toml\"]\n").is_empty());
        assert!(
            collections_in(
                "def run(flag):\n    formats = [\"json\", \"toml\"]\n    if flag:\n        formats = [\"yaml\"]\n    return formats\n",
            )
            .is_empty()
        );
    }

    #[test]
    fn a_mixed_literal_is_not_homogeneous_and_a_call_is_not_a_literal() {
        let found = collections_in(
            "def run():\n    mixed = [\"json\", 2]\n    built = [load()]\n    return mixed, built\n",
        );

        assert_eq!(found[0]["has_homogeneous_literals"], false);
        assert_eq!(found[1]["has_homogeneous_literals"], false);
    }

    #[test]
    fn every_arm_of_a_chain_states_how_much_it_does_and_whether_it_answers() {
        let facts = facts_for(
            "def run(kind, log):\n    if kind == \"pbs\":\n        return 1\n    elif kind == \"slurm\":\n        log(kind)\n        return 2\n    elif kind == \"ssh\":\n        log(kind)\n    else:\n        return 0\n",
            "BranchFact",
        );
        let arms = facts[0]["chains"][0]["arms"].as_array().unwrap();

        assert_eq!(facts[0]["chains"][0]["has_fallback"], true);
        assert_eq!(
            arms.iter()
                .map(|arm| arm["statement_count"].as_u64().unwrap_or_default())
                .collect::<Vec<_>>(),
            [1, 2, 1]
        );
        assert_eq!(
            arms.iter()
                .map(|arm| arm["returns_value"].as_bool().unwrap_or_default())
                .collect::<Vec<_>>(),
            [true, true, false]
        );
    }
}
