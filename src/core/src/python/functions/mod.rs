use crate::functions::FunctionRecord;
use crate::source::Source;
use crate::walk::{blocks, body_range, docstring, expressions, qualified_name, statements};
use ruff_python_ast::{Expr, ModModule, Stmt, StmtClassDef, StmtFunctionDef};
use ruff_text_size::Ranged;
use std::collections::BTreeSet;

mod analysis;
mod asyncio;
mod collector;
mod references;
pub(super) mod support;

use super::reference_index::ReferenceIndex;
use collector::FunctionCollector;
use references::call_sites;
use support::{
    BINDING_DECORATORS, LIFECYCLE_NAMES, MODEL_FOUNDATIONS, ModuleContext, PythonName,
    VALIDATION_EXCEPTIONS, VALIDATOR_DECORATORS, base_names, body_expression, control_increments,
    decorator_name, decorator_texts, descend, executable, is_behavior, is_protocol_name,
    parameters, returns_query_plan, root_name,
};

pub fn function_facts(source: &Source, module: &ModModule) -> Vec<FunctionRecord> {
    let mut collector = FunctionCollector::new(source, module);
    collect_functions(&mut collector, &module.body, None, "module");
    let mut facts = collector.facts;
    let sites = call_sites(source, module);
    let loads = ReferenceIndex::of(module).loads;
    for fact in &mut facts {
        let called = sites
            .get(&fact.identity.name)
            .map(Vec::as_slice)
            .unwrap_or_default();
        fact.measures.reference_count =
            loads.get(&fact.identity.name).copied().unwrap_or_default();
        fact.presentation.nodes.references = called.iter().map(|site| site.node.clone()).collect();
        fact.semantics.roles.is_first_class_reference =
            fact.measures.reference_count > called.len();
        fact.presentation.sole_reference_owner_class = match called {
            [only] => only.owner.clone(),
            _ => String::new(),
        };
        fact.presentation.nodes.sole_reference_owner_definition = match called {
            [only] => only.owner_definition.clone(),
            _ => None,
        };
    }
    facts
}

fn collect_functions<'a>(
    collector: &mut FunctionCollector<'_>,
    body: &'a [Stmt],
    owner: Option<&'a StmtClassDef>,
    scope: &str,
) {
    for statement in body {
        match statement {
            Stmt::FunctionDef(item) => {
                collector.facts.push(
                    Callable::new(collector.source, item, owner, scope, &collector.context)
                        .fact(statement),
                );
                collect_functions(collector, &item.body, None, "nested");
            }
            Stmt::ClassDef(item) => {
                collect_functions(collector, &item.body, Some(item), "method");
            }
            _ => {}
        }
    }
}

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
    context: &'a ModuleContext,
    decorators: Vec<String>,
    body: &'a [Stmt],
}

impl<'a> Callable<'a> {
    fn new(
        source: &'a Source,
        item: &'a StmtFunctionDef,
        owner: Option<&'a StmtClassDef>,
        scope: &'a str,
        context: &'a ModuleContext,
    ) -> Self {
        Self {
            source,
            item,
            owner,
            scope,
            context,
            decorators: decorator_texts(source, &item.decorator_list),
            body: executable(&item.body),
        }
    }

    /// Return the cache this callable is stored in, when a decorator puts it in one.
    fn cache_decorator(&self) -> &'static str {
        ["cached_property", "cache", "lru_cache"]
            .into_iter()
            .find(|named| self.wears(&[named]))
            .unwrap_or_default()
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

    /// Return every call whose callee this file bound to one of the named asyncio entry points.
    fn calls_spelled(&self, spellings: &BTreeSet<String>) -> Vec<&'a ruff_python_ast::ExprCall> {
        self.calls()
            .into_iter()
            .filter(|call| spellings.contains(&qualified_name(&call.func)))
            .collect()
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

    /// Whether one expression is a call this file bound to an asyncio task creator.
    fn creates_task(&self, expression: &Expr) -> bool {
        matches!(expression, Expr::Call(call)
            if self.context.asyncio.creators.contains(&qualified_name(&call.func)))
    }

    /// Return every call in the executable body that schedules work on the event loop.
    fn creations(&self) -> Vec<&'a ruff_python_ast::ExprCall> {
        self.calls_spelled(&self.context.asyncio.creators)
    }

    /// Attach evidence about scheduling and joining asynchronous work.
    fn describe_async(&self, fact: &mut FunctionRecord, expressions: &[&Expr]) {
        fact.structure.created_task_count = self.creations().len();
        fact.measures.has_task_group = expressions.iter().any(|expression| {
            self.context
                .asyncio
                .groups
                .contains(&qualified_name(expression))
        });
        fact.measures.gather_returns_exceptions = self.gather_returns_exceptions();
        fact.measures.gather_consumes_created_tasks = self.gather_consumes_created_tasks();
    }

    /// Attach evidence about behavior performed by the callable body.
    fn describe_behavior(&self, fact: &mut FunctionRecord, expressions: &[&Expr]) {
        fact.semantics.roles.is_recursive = self.is_recursive();
        fact.measures.reads_receiver = self.reads_receiver();
        fact.measures.behavior_operation_count = expressions
            .iter()
            .filter(|expression| is_behavior(expression))
            .count();
        fact.validation.output.returns_single_call = self.returned_call().is_some();
        fact.validation.output.forwards_only_parameter_unchanged = self.forwards_only_parameter();
        fact.validation.input.checks_raw_input_type = self.checks_raw_input_type();
        fact.validation.input.raises_validation_exception = self.raises_validation_exception();
        fact.validation.output.constructs_owner_model = self.constructs_owner_model();
    }

    /// Attach statement and control-flow measurements.
    fn describe_complexity(&self, fact: &mut FunctionRecord) {
        let increments = control_increments(&self.item.body, 0);
        fact.structure.implementation_lines = self.implementation_lines();
        fact.structure.direct_statement_count = self.body.len();
        fact.measures.conditional_count = increments
            .iter()
            .filter(|increment| increment.kind == "conditional")
            .count();
        fact.structure.control_increments = increments;
        fact.semantics.outcomes.is_declarative_body = self.wears(&["rule"])
            || fact.structure.control_increments.is_empty() && returns_query_plan(self.item);
    }

    /// Attach meanings established by decorators and the containing class.
    fn describe_decorators(&self, fact: &mut FunctionRecord) {
        let owner_bases = self.owner_bases();
        fact.semantics.outcomes.is_property =
            self.wears(&["property", "cached_property", "setter", "getter", "deleter"]);
        fact.semantics.roles.is_abstract = self.wears(&["abstractmethod", "abstractproperty"]);
        fact.semantics.outcomes.is_overload = self.wears(&["overload"]);
        fact.semantics.outcomes.is_polymorphic = self.wears(&["override"]);
        fact.validation.input.is_pydantic_validator = self.wears(VALIDATOR_DECORATORS);
        fact.presentation.cache_decorator = self.cache_decorator().to_string();
        fact.semantics.outcomes.is_protocol_member =
            owner_bases.iter().any(|base| base == "Protocol");
        fact.validation.input.is_model_method = owner_bases
            .iter()
            .any(|base| MODEL_FOUNDATIONS.contains(&base.as_str()));
    }

    /// Attach the source nodes and executable body shapes.
    fn describe_source(&self, fact: &mut FunctionRecord, statement: &Stmt) {
        fact.presentation.nodes.definition = Some(self.source.node_of("function", statement));
        fact.presentation.nodes.body_expression = body_expression(self.source, &self.item.body);
        fact.presentation.docstring = docstring(&self.item.body).unwrap_or_default();
        fact.semantics.outcomes.is_pass_body =
            self.body.len() == 1 && matches!(self.body[0], Stmt::Pass(_));
        fact.validation.output.is_raise_body =
            self.body.len() == 1 && matches!(self.body[0], Stmt::Raise(_));
    }

    /// Attach the roles and contracts carried by tensor annotations.
    fn describe_tensors(&self, fact: &mut FunctionRecord) {
        let tensors = self.tensor_roles();
        fact.structure.recognized_tensor_roles = tensors.roles;
        fact.semantics.roles.has_tensor_shape_semantics = tensors.states_shape;
        fact.semantics.roles.has_tensor_dtype_semantics = tensors.states_dtype;
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

    /// State one callable as the fact every function rule reads.
    fn fact(&self, statement: &Stmt) -> FunctionRecord {
        let expressions = self.expressions();
        let mut fact = self.fact_identity(statement);
        self.describe_async(&mut fact, &expressions);
        self.describe_behavior(&mut fact, &expressions);
        self.describe_complexity(&mut fact);
        self.describe_decorators(&mut fact);
        self.describe_source(&mut fact, statement);
        self.describe_tensors(&mut fact);
        fact
    }

    /// Start the record with the identity and callable contract visible at its declaration.
    fn fact_identity(&self, statement: &Stmt) -> FunctionRecord {
        let name = self.item.name.to_string();
        let mut fact =
            FunctionRecord::new(self.source.span(statement.range()), "python", name.clone());
        fact.identity.scope = self.scope.to_string();
        fact.presentation.visibility = name.visibility_in(self.scope).to_string();
        fact.semantics.roles.is_protocol_name = is_protocol_name(&name);
        fact.semantics.roles.is_async = self.item.is_async;
        fact.structure.parameters = parameters(self.source, &self.item.parameters);
        fact.structure.decorators = self.decorators.clone();
        fact.semantics.outcomes.is_framework_hook = self.is_framework_hook();
        fact
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

    /// Whether a gather in the body waits on the very tasks this callable created.
    ///
    /// Both shapes a reader writes arrive here. The tasks are gathered where they were made, or
    /// they were bound to a name first and the gather names that binding instead.
    fn gather_consumes_created_tasks(&self) -> bool {
        let created = self.created_task_bindings();
        self.calls_spelled(&self.context.asyncio.gathers)
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

    /// Whether any awaited gather in the body was told to hand failures back as values.
    fn gather_returns_exceptions(&self) -> bool {
        self.calls_spelled(&self.context.asyncio.gathers)
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

    /// Return the plain name of every base the class holding this callable states.
    fn owner_bases(&self) -> Vec<String> {
        self.owner
            .map(|owner| base_names(self.source, owner))
            .unwrap_or_default()
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

    /// Whether the executable body ever reads the instance or class it was handed.
    fn reads_receiver(&self) -> bool {
        self.receiver().is_some_and(|receiver| self.loads(receiver))
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

    /// Whether this callable wears one of the named decorators, however it was imported.
    fn wears(&self, names: &[&str]) -> bool {
        self.decorators
            .iter()
            .any(|decorator| names.contains(&decorator_name(decorator)))
    }
}
